# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError

CASH_FLOW_ACCOUNT_TYPES = ("asset_receivable", "liability_payable")


class ResCompany(models.Model):
    _inherit = "res.company"

    cash_flow_horizon_months = fields.Integer(
        string="Cash Flow Forecast Horizon (Months)",
        default=12,
        help="Forecast lines are generated up to this many months ahead.",
    )
    cash_flow_vat_forecast = fields.Boolean(
        string="Forecast VAT Payments",
        default=True,
    )
    cash_flow_vat_period = fields.Selection(
        selection=[
            ("month", "Month"),
            ("quarter", "Quarter"),
            ("year", "Year"),
        ],
        string="VAT Period",
        default="month",
        required=True,
    )
    cash_flow_vat_due_months = fields.Integer(
        string="VAT Due Months",
        default=2,
        help="The VAT of a period is due this many months after the month the "
        "period ends in.",
    )
    cash_flow_vat_due_day = fields.Integer(
        string="VAT Due Day",
        default=12,
        help="Day of the month the VAT is due. A day past the end of the month "
        "means the last day of the month.",
    )
    cash_flow_vat_estimate_periods = fields.Integer(
        string="VAT Estimate History (Periods)",
        default=3,
        help="The VAT of the current and future periods is estimated from the "
        "average of this many past periods. 0 forecasts only VAT already "
        "booked.",
    )
    cash_flow_vat_account_id = fields.Many2one(
        comodel_name="account.account",
        string="VAT Forecast Account",
        domain=[("account_type", "in", CASH_FLOW_ACCOUNT_TYPES)],
        help="Receivable or payable account the VAT forecast lines are shown "
        "on. Empty: the tax payable account of the company's tax groups.",
    )

    @api.constrains(
        "cash_flow_horizon_months",
        "cash_flow_vat_due_months",
        "cash_flow_vat_due_day",
        "cash_flow_vat_estimate_periods",
    )
    def _check_cash_flow_settings(self):
        for company in self:
            if company.cash_flow_horizon_months < 1:
                raise ValidationError(
                    self.env._(
                        "The cash flow forecast horizon must be at least a month."
                    )
                )
            if not 1 <= company.cash_flow_vat_due_day <= 31:
                raise ValidationError(
                    self.env._("The VAT due day must be between 1 and 31.")
                )
            if (
                company.cash_flow_vat_due_months < 0
                or company.cash_flow_vat_estimate_periods < 0
            ):
                raise ValidationError(
                    self.env._(
                        "The VAT due months and estimate periods cannot be negative."
                    )
                )

    def _get_cash_flow_vat_accounts(self):
        """Accounts that hold the VAT of a period until it is settled: the
        accounts of the tax repartition lines of the company's taxes."""
        self.ensure_one()
        lines = self.env["account.tax.repartition.line"].search(
            [
                ("company_id", "=", self.id),
                ("repartition_type", "=", "tax"),
                ("account_id", "!=", False),
            ]
        )
        return lines.account_id.filtered(
            lambda a: a.account_type
            not in CASH_FLOW_ACCOUNT_TYPES + ("asset_cash", "liability_credit_card")
        )

    def _get_cash_flow_vat_forecast_account(self):
        self.ensure_one()
        if self.cash_flow_vat_account_id:
            return self.cash_flow_vat_account_id
        groups = self.env["account.tax.group"].search(
            [
                ("company_id", "=", self.id),
                ("tax_payable_account_id.account_type", "=", "liability_payable"),
            ],
            limit=1,
        )
        return groups.tax_payable_account_id
