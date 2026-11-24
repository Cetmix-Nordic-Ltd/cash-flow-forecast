# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

PERIOD_MONTHS = {"month": 1, "quarter": 3, "year": 12}


class MisCashFlowForecastLine(models.Model):
    _inherit = "mis.cash_flow.forecast_line"
    _order = "date, id"

    source = fields.Selection(
        selection=[
            ("manual", "Manual"),
            ("recurring", "Recurring Cost"),
            ("vat", "VAT"),
        ],
        default="manual",
        required=True,
        index=True,
        help="Lines of any other source than Manual are generated: they are "
        "replaced every time the forecast is updated.",
    )
    res_model = fields.Char(string="Origin Model", readonly=True)
    res_id = fields.Many2oneReference(
        string="Origin ID", model_field="res_model", readonly=True
    )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @api.model
    def _cron_generate_auto_lines(self):
        for company in self.env["res.company"].search([]):
            self.with_company(company)._generate_auto_lines(company)

    def action_generate_auto_lines(self):
        """Update the generated lines of the user's selected companies."""
        for company in self.env.companies:
            self.with_company(company)._generate_auto_lines(company)
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_origin(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        record = self.env[self.res_model].browse(self.res_id).exists()
        return record.get_formview_action() if record else False

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _generate_auto_lines(self, company):
        """Replace the generated lines of ``company``. Manual lines stay.

        The sources are read with superuser rights: the forecast is a
        company-wide figure, not limited to the documents the user sees."""
        today = fields.Date.context_today(self)
        date_to = today + relativedelta(months=company.cash_flow_horizon_months)
        sudo_self = self.sudo().with_company(company)
        values = sudo_self._get_auto_line_values(company, today, date_to)
        currency = company.currency_id
        values = [
            dict(vals, company_id=company.id)
            for vals in values
            if vals["date"] <= date_to and not currency.is_zero(vals["balance"])
        ]
        sudo_self.search(
            [("company_id", "=", company.id), ("source", "!=", "manual")]
        ).unlink()
        lines = sudo_self.create(values)
        _logger.info(
            "Cash flow forecast: %s generated lines for %s", len(lines), company.name
        )
        return lines

    def _get_auto_line_values(self, company, date_from, date_to):
        """Values of the generated lines of ``company`` from ``date_from`` to
        ``date_to``. Extend it to add a source; each value dict needs
        ``date``, ``account_id``, ``name``, ``balance`` (company currency,
        positive = money in) and ``source``."""
        rules = self.env["mis.cash_flow.recurring_rule"].search(
            [("company_id", "=", company.id)]
        )
        values = rules._get_forecast_line_values(date_from, date_to)
        if company.cash_flow_vat_forecast:
            values += self._get_vat_forecast_values(company, date_from, date_to)
        return values

    @api.model
    def _cash_flow_split_by_terms(self, payment_term, date_ref, amount, company):
        """``amount`` (company currency) split by ``payment_term`` into
        ``[(date, amount)]``; one line due on ``date_ref`` without a term."""
        if not payment_term or not payment_term.line_ids:
            return [(date_ref, amount)]
        currency = company.currency_id
        terms = payment_term._compute_terms(
            date_ref,
            currency,
            company,
            0.0,
            0.0,
            1 if amount >= 0 else -1,
            amount,
            amount,
        )
        return [(term["date"], term["company_amount"]) for term in terms["line_ids"]]

    # ------------------------------------------------------------------
    # VAT
    # ------------------------------------------------------------------

    @api.model
    def _vat_period_start(self, company, day):
        months = PERIOD_MONTHS[company.cash_flow_vat_period]
        month = (day.month - 1) // months * months + 1
        return day.replace(month=month, day=1)

    @api.model
    def _vat_periods(self, company, date_from, date_to):
        """``(start, end, due date)`` of the VAT periods due from
        ``date_from`` to ``date_to``."""
        months = PERIOD_MONTHS[company.cash_flow_vat_period]
        start = self._vat_period_start(
            company,
            date_from - relativedelta(months=company.cash_flow_vat_due_months + 12),
        )
        periods = []
        while start <= date_to:
            end = start + relativedelta(months=months, days=-1)
            due = end + relativedelta(
                months=company.cash_flow_vat_due_months,
                day=company.cash_flow_vat_due_day,
            )
            if date_from <= due <= date_to:
                periods.append((start, end, due))
            start += relativedelta(months=months)
        return periods

    @api.model
    def _vat_balance(self, company, accounts, date_from, date_to, tax_lines_only):
        domain = [
            ("company_id", "=", company.id),
            ("account_id", "in", accounts.ids),
            ("parent_state", "=", "posted"),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]
        if tax_lines_only:
            domain.append(("tax_line_id", "!=", False))
        groups = self.env["account.move.line"]._read_group(
            domain, aggregates=["balance:sum"]
        )
        return groups[0][0] if groups else 0.0

    @api.model
    def _vat_estimate(self, company, accounts, current_start):
        """Average VAT of the periods before ``current_start``, from the tax
        lines only so that the closing entries of the periods do not count."""
        count = company.cash_flow_vat_estimate_periods
        if not count:
            return 0.0
        months = PERIOD_MONTHS[company.cash_flow_vat_period]
        history_from = current_start - relativedelta(months=months * count)
        total = self._vat_balance(
            company,
            accounts,
            history_from,
            current_start - relativedelta(days=1),
            tax_lines_only=True,
        )
        return total / count

    @api.model
    def _get_vat_forecast_values(self, company, date_from, date_to):
        """One line per VAT period due in the horizon. A closed period is the
        VAT still on the VAT accounts (nothing once the period has been
        settled to the tax authority's payable account, which the cash flow
        report shows itself). The current period adds the estimate for its
        remaining days; future periods are the estimate."""
        account = company._get_cash_flow_vat_forecast_account()
        accounts = company._get_cash_flow_vat_accounts()
        if not account or not accounts:
            _logger.info(
                "Cash flow forecast: no VAT forecast for %s, no VAT forecast "
                "account or VAT accounts",
                company.name,
            )
            return []
        current_start = self._vat_period_start(company, date_from)
        estimate = self._vat_estimate(company, accounts, current_start)
        values = []
        for start, end, due in self._vat_periods(company, date_from, date_to):
            label = (
                f"{start:%Y-%m}"
                if start == end.replace(day=1)
                else (f"{start:%Y-%m}..{end:%Y-%m}")
            )
            if end < date_from:
                balance = self._vat_balance(
                    company, accounts, start, end, tax_lines_only=False
                )
                name = self.env._("VAT %(period)s", period=label)
            elif start <= date_from:
                booked = self._vat_balance(
                    company, accounts, start, end, tax_lines_only=False
                )
                remaining = ((end - date_from).days + 1) / ((end - start).days + 1)
                balance = booked + estimate * remaining
                name = self.env._("VAT %(period)s (partly estimated)", period=label)
            else:
                balance = estimate
                name = self.env._("VAT %(period)s (estimate)", period=label)
            values.append(
                {
                    "date": due,
                    "account_id": account.id,
                    "name": name,
                    "balance": balance,
                    "source": "vat",
                }
            )
        return values
