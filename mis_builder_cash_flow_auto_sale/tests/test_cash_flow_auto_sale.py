# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date, datetime

from odoo import Command
from odoo.tests import Form, freeze_time, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestCashFlowAutoSale(AccountTestInvoicingCommon):
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

    def _order(self, commitment_date):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "payment_term_id": self.term.id,
                "commitment_date": commitment_date,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_uom_qty": 10,
                            "price_unit": 100.0,
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        return order

    def _lines(self):
        return self.Line.search(
            [("company_id", "=", self.company.id), ("source", "=", "sale")]
        )

    @freeze_time("2026-11-10")
    def test_sale_order_forecast(self):
        order = self._order(datetime(2026, 12, 1, 12, 0))
        self.env["sale.order"].create({"partner_id": self.partner_a.id})
        self.Line._generate_auto_lines(self.company)
        line = self._lines()
        self.assertEqual(len(line), 1)
        self.assertEqual(line.date, date(2026, 12, 31))
        self.assertAlmostEqual(line.balance, order.amount_total)
        self.assertEqual(line.account_id, self.partner_a.property_account_receivable_id)
        self.assertEqual((line.res_model, line.res_id), ("sale.order", order.id))

    @freeze_time("2026-11-10")
    def test_past_delivery_and_posted_invoice(self):
        order = self._order(datetime(2026, 10, 1, 12, 0))
        # A draft invoice does not count
        invoice = order._create_invoices()
        self.Line._generate_auto_lines(self.company)
        self.assertAlmostEqual(self._lines().balance, order.amount_total)
        # Due 30 days from today, as the delivery date has passed
        self.assertEqual(self._lines().date, date(2026, 12, 10))
        # Posting 4 of 10 leaves 6 to forecast
        with Form(invoice) as form:
            with form.invoice_line_ids.edit(0) as line_form:
                line_form.quantity = 4
        invoice.action_post()
        self.Line._generate_auto_lines(self.company)
        self.assertAlmostEqual(self._lines().balance, order.amount_total * 0.6)
        # Fully invoiced orders are not forecast
        rest = order._create_invoices()
        rest.action_post()
        self.Line._generate_auto_lines(self.company)
        self.assertFalse(self._lines())
