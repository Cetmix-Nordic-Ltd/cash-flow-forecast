# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from odoo import Command
from odoo.tests import freeze_time, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestCashFlowAutoContract(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.company_data["company"]
        cls.company.write(
            {"cash_flow_horizon_months": 3, "cash_flow_vat_forecast": False}
        )
        cls.Line = cls.env["mis.cash_flow.forecast_line"]

    def _contract(self, contract_type, product, date_end=False):
        return self.env["contract.contract"].create(
            {
                "name": f"Test {contract_type}",
                "partner_id": self.partner_a.id,
                "contract_type": contract_type,
                "line_recurrence": True,
                "contract_line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "name": "Service",
                            "quantity": 1,
                            "uom_id": product.uom_id.id,
                            "price_unit": 100.0,
                            "recurring_rule_type": "monthly",
                            "recurring_interval": 1,
                            "recurring_invoicing_type": "pre-paid",
                            "date_start": date(2026, 11, 1),
                            "recurring_next_date": date(2026, 11, 1),
                            "date_end": date_end,
                        }
                    )
                ],
            }
        )

    def _lines(self, contract):
        return self.Line.search(
            [("source", "=", "contract"), ("res_id", "=", contract.id)], order="date"
        )

    @freeze_time("2026-11-10")
    def test_sale_contract(self):
        contract = self._contract("sale", self.product_a)
        self.Line._generate_auto_lines(self.company)
        lines = self._lines(contract)
        # November (not yet invoiced: today), December, January, February
        self.assertEqual(
            lines.mapped("date"),
            [date(2026, 11, 10), date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1)],
        )
        tax = self.product_a.sudo().taxes_id.filtered(
            lambda t: t.company_id == self.company
        )
        expected = tax.compute_all(100.0)["total_included"] if tax else 100.0
        for line in lines:
            self.assertAlmostEqual(line.balance, expected)
        self.assertEqual(
            lines.account_id, self.partner_a.property_account_receivable_id
        )

    @freeze_time("2026-11-10")
    def test_purchase_contract_with_end(self):
        contract = self._contract("purchase", self.product_a, date(2026, 12, 31))
        self.Line._generate_auto_lines(self.company)
        lines = self._lines(contract)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.balance < 0 for line in lines))
        self.assertEqual(lines.account_id, self.partner_a.property_account_payable_id)

    @freeze_time("2026-11-10")
    def test_canceled_line(self):
        contract = self._contract("sale", self.product_a)
        contract.contract_line_ids.is_canceled = True
        self.Line._generate_auto_lines(self.company)
        self.assertFalse(self._lines(contract))
