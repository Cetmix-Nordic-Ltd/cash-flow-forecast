# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cash_flow_horizon_months = fields.Integer(
        related="company_id.cash_flow_horizon_months", readonly=False
    )
    cash_flow_vat_forecast = fields.Boolean(
        related="company_id.cash_flow_vat_forecast", readonly=False
    )
    cash_flow_vat_period = fields.Selection(
        related="company_id.cash_flow_vat_period", readonly=False
    )
    cash_flow_vat_due_months = fields.Integer(
        related="company_id.cash_flow_vat_due_months", readonly=False
    )
    cash_flow_vat_due_day = fields.Integer(
        related="company_id.cash_flow_vat_due_day", readonly=False
    )
    cash_flow_vat_estimate_periods = fields.Integer(
        related="company_id.cash_flow_vat_estimate_periods", readonly=False
    )
    cash_flow_vat_account_id = fields.Many2one(
        related="company_id.cash_flow_vat_account_id", readonly=False
    )
