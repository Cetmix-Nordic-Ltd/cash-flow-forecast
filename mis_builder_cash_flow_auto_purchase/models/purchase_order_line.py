# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def _get_cash_flow_amount_to_bill(self):
        """Amount (taxes included, order currency) of the ordered quantity
        not yet on a posted bill. Draft bills do not count: they are not in
        the cash flow report either."""
        self.ensure_one()
        if self.display_type or not self.product_qty:
            return 0.0
        billed = 0.0
        for inv_line in self.invoice_lines:
            move = inv_line.move_id
            if move.state != "posted":
                continue
            qty = inv_line.product_uom_id._compute_quantity(
                inv_line.quantity, self.product_uom
            )
            billed += -qty if move.move_type == "in_refund" else qty
        remaining = self.product_qty - billed
        if remaining <= 0:
            return 0.0
        return self.price_total * remaining / self.product_qty
