# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date, datetime

from odoo import Command
from odoo.tests import freeze_time, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestCashFlowAutoPurchase(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.company_data["company"]
        cls.company.write(
            {"cash_flow_horizon_months": 6, "cash_flow_vat_forecast": False}
        )
        cls.Line = cls.env["mis.cash_flow.forecast_line"]
        cls.term = cls.env.ref("account.account_payment_term_30days")

    def _order(self):
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "payment_term_id": self.term.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 10,
                            "price_unit": 100.0,
                            "date_planned": datetime(2026, 12, 1, 12, 0),
                        }
                    )
                ],
            }
        )
        order.button_confirm()
        return order

    def _bill(self, order_line, quantity, post):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": date(2026, 11, 10),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": order_line.product_id.id,
                            "quantity": quantity,
                            "price_unit": order_line.price_unit,
                            "tax_ids": [Command.set(order_line.taxes_id.ids)],
                            "purchase_line_id": order_line.id,
                        }
                    )
                ],
            }
        )
        if post:
            bill.action_post()
        return bill

    def _lines(self):
        return self.Line.search(
            [("company_id", "=", self.company.id), ("source", "=", "purchase")]
        )

    @freeze_time("2026-11-10")
    def test_purchase_order_forecast(self):
        order = self._order()
        self.Line._generate_auto_lines(self.company)
        line = self._lines()
        self.assertEqual(len(line), 1)
        self.assertEqual(line.date, date(2026, 12, 31))
        self.assertAlmostEqual(line.balance, -order.amount_total)
        self.assertEqual(line.account_id, self.partner_a.property_account_payable_id)
        self.assertEqual((line.res_model, line.res_id), ("purchase.order", order.id))

    @freeze_time("2026-11-10")
    def test_posted_bills_only(self):
        order = self._order()
        order_line = order.order_line
        self._bill(order_line, 4, post=False)
        self.assertEqual(order_line._get_cash_flow_amount_to_bill(), order.amount_total)
        self._bill(order_line, 4, post=True)
        self.assertAlmostEqual(
            order_line._get_cash_flow_amount_to_bill(), order.amount_total * 0.6
        )
        self.Line._generate_auto_lines(self.company)
        self.assertAlmostEqual(self._lines().balance, -order.amount_total * 0.6)
        self._bill(order_line, 6, post=True)
        self.Line._generate_auto_lines(self.company)
        self.assertFalse(self._lines())
