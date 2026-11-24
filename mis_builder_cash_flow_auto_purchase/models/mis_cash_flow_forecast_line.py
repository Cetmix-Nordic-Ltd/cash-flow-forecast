# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import fields, models


class MisCashFlowForecastLine(models.Model):
    _inherit = "mis.cash_flow.forecast_line"

    source = fields.Selection(
        selection_add=[("purchase", "Purchase Order")],
        ondelete={"purchase": "cascade"},
    )

    def _get_auto_line_values(self, company, date_from, date_to):
        values = super()._get_auto_line_values(company, date_from, date_to)
        return values + self._get_purchase_forecast_values(company, date_from, date_to)

    def _get_purchase_forecast_values(self, company, date_from, date_to):
        """The amount not yet on a posted bill of each order line, billed on
        the line's expected arrival and paid by the order's payment terms
        (or the vendor's)."""
        lines = self.env["purchase.order.line"].search(
            [
                ("company_id", "=", company.id),
                ("order_id.state", "in", ("purchase", "done")),
                ("display_type", "=", False),
            ]
        )
        by_order_date = defaultdict(float)
        for line in lines:
            amount = line._get_cash_flow_amount_to_bill()
            if not amount:
                continue
            bill_date = max(fields.Date.to_date(line.date_planned), date_from)
            by_order_date[(line.order_id, bill_date)] += amount
        values = []
        for (order, bill_date), amount in by_order_date.items():
            amount = order.currency_id._convert(
                amount, company.currency_id, company, date_from
            )
            if company.currency_id.compare_amounts(amount, 0.0) <= 0:
                continue
            partner = order.partner_id.commercial_partner_id.with_company(company)
            term = order.payment_term_id or partner.property_supplier_payment_term_id
            for due, part in self._cash_flow_split_by_terms(
                term, bill_date, -amount, company
            ):
                values.append(
                    {
                        "date": max(due, date_from),
                        "account_id": partner.property_account_payable_id.id,
                        "partner_id": partner.id,
                        "name": order.name,
                        "balance": part,
                        "source": "purchase",
                        "res_model": order._name,
                        "res_id": order.id,
                    }
                )
        return values
