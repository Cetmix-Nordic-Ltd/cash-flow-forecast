# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import models


class ContractLine(models.Model):
    _inherit = "contract.line"

    def _get_cash_flow_invoice_dates(self, date_to):
        """Dates of the coming invoices of the line up to ``date_to``,
        following the contract's own recurrence rules."""
        self.ensure_one()
        dates = []
        invoice_date = self.recurring_next_date
        period_start = self.next_period_date_start
        while invoice_date and period_start and invoice_date <= date_to:
            period_end = self.get_next_period_date_end(
                period_start,
                self.recurring_rule_type,
                self.recurring_interval,
                max_date_end=self.date_end,
            )
            if not period_end:
                break
            dates.append(invoice_date)
            period_start = period_end + relativedelta(days=1)
            invoice_date = self.get_next_invoice_date(
                period_start,
                self.recurring_invoicing_type,
                self.recurring_invoicing_offset,
                self.recurring_rule_type,
                self.recurring_interval,
                max_date_end=self.date_end,
            )
        return dates

    def _get_cash_flow_amount(self):
        """Amount of one invoice of the line, taxes included, in the
        contract's currency."""
        self.ensure_one()
        contract = self.contract_id
        if contract.contract_type == "purchase":
            taxes = self.product_id.supplier_taxes_id
        else:
            taxes = self.product_id.taxes_id
        taxes = taxes.filtered(lambda t: t.company_id == contract.company_id)
        if contract.fiscal_position_id:
            taxes = contract.fiscal_position_id.map_tax(taxes)
        if not taxes:
            return self.price_subtotal
        return taxes.compute_all(
            self.price_subtotal,
            currency=contract.currency_id,
            product=self.product_id,
            partner=contract.partner_id,
        )["total_included"]
