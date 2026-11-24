# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class MisCashFlowForecastLine(models.Model):
    _inherit = "mis.cash_flow.forecast_line"

    source = fields.Selection(
        selection_add=[("sale", "Sales Order")],
        ondelete={"sale": "cascade"},
    )

    def _get_auto_line_values(self, company, date_from, date_to):
        values = super()._get_auto_line_values(company, date_from, date_to)
        return values + self._get_sale_forecast_values(company, date_from, date_to)

    def _get_sale_forecast_values(self, company, date_from, date_to):
        """The un-invoiced amount (taxes included, posted invoices
        deducted) of each confirmed order, invoiced on the delivery date
        and paid by the order's payment terms."""
        orders = self.env["sale.order"].search(
            [
                ("company_id", "=", company.id),
                ("state", "=", "sale"),
            ]
        )
        values = []
        for order in orders:
            amount = order.currency_id._convert(
                order.amount_to_invoice, company.currency_id, company, date_from
            )
            if company.currency_id.compare_amounts(amount, 0.0) <= 0:
                continue
            invoice_date = max(
                fields.Date.to_date(
                    order.commitment_date or order.expected_date or order.date_order
                ),
                date_from,
            )
            partner = order.partner_invoice_id.commercial_partner_id
            account = partner.with_company(company).property_account_receivable_id
            for due, part in self._cash_flow_split_by_terms(
                order.payment_term_id, invoice_date, amount, company
            ):
                values.append(
                    {
                        "date": max(due, date_from),
                        "account_id": account.id,
                        "partner_id": partner.id,
                        "name": order.name,
                        "balance": part,
                        "source": "sale",
                        "res_model": order._name,
                        "res_id": order.id,
                    }
                )
        return values
