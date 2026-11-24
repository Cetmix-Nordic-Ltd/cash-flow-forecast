# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .res_company import CASH_FLOW_ACCOUNT_TYPES


class MisCashFlowRecurringRule(models.Model):
    """A cost or income that recurs every month, e.g. wages or rent,
    forecast as the monthly average of its recent history."""

    _name = "mis.cash_flow.recurring_rule"
    _description = "MIS Cash Flow Recurring Rule"
    _order = "sequence, id"
    _check_company_auto = True

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    account_ids = fields.Many2many(
        comodel_name="account.account",
        string="Accounts",
        required=True,
        check_company=True,
        help="Accounts whose postings are averaged, e.g. the wage accounts.",
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Partners",
        help="Only postings with these partners count. Empty: all postings.",
    )
    history_months = fields.Integer(
        string="History (Months)",
        default=3,
        required=True,
        help="Number of past full months the average is taken over.",
    )
    day_of_month = fields.Integer(
        default=15,
        required=True,
        help="Day of the month the payment is expected. A day past the end of "
        "the month means the last day of the month.",
    )
    forecast_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Forecast Account",
        required=True,
        check_company=True,
        domain=[("account_type", "in", CASH_FLOW_ACCOUNT_TYPES)],
        help="Receivable or payable account the forecast lines are shown on "
        "in the cash flow report.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Forecast Partner",
        help="Partner of the forecast lines, e.g. the landlord.",
    )
    monthly_amount = fields.Monetary(
        compute="_compute_monthly_amount",
        currency_field="currency_id",
        help="Average monthly cash flow: negative for a cost.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    @api.constrains("history_months", "day_of_month")
    def _check_numbers(self):
        for rule in self:
            if rule.history_months < 1:
                raise ValidationError(
                    self.env._("The history must be at least one month.")
                )
            if not 1 <= rule.day_of_month <= 31:
                raise ValidationError(
                    self.env._("The day of the month must be between 1 and 31.")
                )

    @api.depends("account_ids", "partner_ids", "history_months", "company_id")
    def _compute_monthly_amount(self):
        today = fields.Date.context_today(self)
        for rule in self:
            rule.monthly_amount = rule._get_monthly_amount(today.replace(day=1))

    def _get_move_line_domain(self, date_from, date_to):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("account_id", "in", self.account_ids.ids),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        return domain

    def _get_monthly_amount(self, first_month):
        """Average monthly cash flow of the full months before
        ``first_month``: the opposite of the average balance, so a cost is
        negative."""
        self.ensure_one()
        if not self.account_ids or self.history_months < 1:
            return 0.0
        domain = self._get_move_line_domain(
            first_month - relativedelta(months=self.history_months),
            first_month - relativedelta(days=1),
        ) + [("parent_state", "=", "posted")]
        groups = (
            self.env["account.move.line"]
            .sudo()
            ._read_group(domain, aggregates=["balance:sum"])
        )
        total = groups[0][0] if groups else 0.0
        return -self.company_id.currency_id.round(total / self.history_months)

    def _has_postings(self, month_start):
        """True if the month already has postings on the rule's accounts:
        they are already in the cash flow as open payables or receivables."""
        self.ensure_one()
        domain = self._get_move_line_domain(
            month_start, month_start + relativedelta(months=1, days=-1)
        ) + [("parent_state", "!=", "cancel")]
        return bool(self.env["account.move.line"].sudo().search_count(domain, limit=1))

    def _get_forecast_line_values(self, date_from, date_to):
        values = []
        first_month = date_from.replace(day=1)
        for rule in self:
            amount = rule._get_monthly_amount(first_month)
            if rule.company_id.currency_id.is_zero(amount):
                continue
            month = first_month
            while month <= date_to:
                if not rule._has_postings(month):
                    due = month + relativedelta(day=rule.day_of_month)
                    values.append(
                        {
                            "date": max(due, date_from),
                            "account_id": rule.forecast_account_id.id,
                            "partner_id": rule.partner_id.id,
                            "name": f"{rule.name} {month:%Y-%m}",
                            "balance": amount,
                            "source": "recurring",
                            "res_model": rule._name,
                            "res_id": rule.id,
                        }
                    )
                month += relativedelta(months=1)
        return values
