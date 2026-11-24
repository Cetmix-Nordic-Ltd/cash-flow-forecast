# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import freeze_time, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestCashFlowAuto(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.company_data["company"]
        cls.company.write(
            {
                "cash_flow_horizon_months": 3,
                "cash_flow_vat_forecast": False,
                "cash_flow_vat_period": "month",
                "cash_flow_vat_due_months": 2,
                "cash_flow_vat_due_day": 12,
                "cash_flow_vat_estimate_periods": 0,
            }
        )
        cls.payable = cls.company_data["default_account_payable"]
        cls.expense = cls.company_data["default_account_expense"]
        cls.Line = cls.env["mis.cash_flow.forecast_line"]
        cls.rule = cls.env["mis.cash_flow.recurring_rule"].create(
            {
                "name": "Rent",
                "company_id": cls.company.id,
                "account_ids": [Command.set(cls.expense.ids)],
                "history_months": 2,
                "day_of_month": 31,
                "forecast_account_id": cls.payable.id,
            }
        )
        cls.manual = cls.Line.create(
            {
                "date": date(2026, 12, 1),
                "account_id": cls.payable.id,
                "name": "Manual",
                "balance": -10.0,
                "company_id": cls.company.id,
            }
        )

    def _post_expense(self, day, amount):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": day,
                "line_ids": [
                    Command.create(
                        {"account_id": self.expense.id, "debit": amount, "name": "x"}
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_assets"
                            ].id,
                            "credit": amount,
                            "name": "x",
                        }
                    ),
                ],
            }
        )
        move.action_post()
        return move

    def _generated(self, source):
        return self.Line.search(
            [("company_id", "=", self.company.id), ("source", "=", source)],
            order="date",
        )

    @freeze_time("2026-11-10")
    def test_recurring_rule(self):
        self._post_expense(date(2026, 9, 5), 1000.0)
        self._post_expense(date(2026, 10, 5), 1400.0)
        self.assertEqual(self.rule.monthly_amount, -1200.0)
        self.Line._generate_auto_lines(self.company)
        lines = self._generated("recurring")
        # November to February; no posting yet in November
        self.assertEqual(
            lines.mapped("date"),
            [date(2026, 11, 30), date(2026, 12, 31), date(2027, 1, 31)],
        )
        self.assertEqual(set(lines.mapped("balance")), {-1200.0})
        self.assertEqual(lines[0].res_model, "mis.cash_flow.recurring_rule")
        self.assertEqual(lines[0].res_id, self.rule.id)
        self.assertTrue(self.manual.exists())

    @freeze_time("2026-11-10")
    def test_recurring_rule_skips_posted_month(self):
        self._post_expense(date(2026, 9, 5), 1000.0)
        self._post_expense(date(2026, 11, 2), 1000.0)
        self.Line._generate_auto_lines(self.company)
        months = [d.month for d in self._generated("recurring").mapped("date")]
        self.assertNotIn(11, months)
        self.assertIn(12, months)

    @freeze_time("2026-11-10")
    def test_regenerate_replaces_generated_lines(self):
        self._post_expense(date(2026, 10, 5), 600.0)
        self.Line._generate_auto_lines(self.company)
        first = self._generated("recurring")
        self.Line._generate_auto_lines(self.company)
        second = self._generated("recurring")
        self.assertFalse(first.exists())
        self.assertEqual(len(first), len(second))
        self.assertTrue(self.manual.exists())

    def test_vat_periods(self):
        Line = self.Line
        periods = Line._vat_periods(self.company, date(2026, 11, 10), date(2027, 2, 10))
        self.assertEqual(
            [(p[0], p[2]) for p in periods],
            [
                (date(2026, 9, 1), date(2026, 11, 12)),
                (date(2026, 10, 1), date(2026, 12, 12)),
                (date(2026, 11, 1), date(2027, 1, 12)),
            ],
        )
        self.company.cash_flow_vat_period = "quarter"
        periods = Line._vat_periods(self.company, date(2026, 11, 10), date(2027, 6, 1))
        self.assertEqual(
            [(p[0], p[2]) for p in periods],
            [
                (date(2026, 7, 1), date(2026, 11, 12)),
                (date(2026, 10, 1), date(2027, 2, 12)),
                (date(2027, 1, 1), date(2027, 5, 12)),
            ],
        )

    @freeze_time("2026-11-10")
    def test_vat_forecast(self):
        self.company.write(
            {
                "cash_flow_horizon_months": 4,
                "cash_flow_vat_forecast": True,
                "cash_flow_vat_estimate_periods": 1,
                "cash_flow_vat_account_id": self.payable.id,
            }
        )
        tax = self.company_data["default_tax_sale"]
        for invoice_date, price in (
            (date(2026, 10, 15), 1000.0),
            (date(2026, 11, 3), 500.0),
        ):
            invoice = self.init_invoice(
                "out_invoice",
                invoice_date=invoice_date,
                amounts=[price],
                taxes=tax,
                post=True,
            )
            self.assertTrue(invoice.amount_tax)
        october_tax = -1000.0 * tax.amount / 100
        november_tax = -500.0 * tax.amount / 100
        self.Line._generate_auto_lines(self.company)
        lines = self._generated("vat")
        by_date = {line.date: line.balance for line in lines}
        account = self.company._get_cash_flow_vat_forecast_account()
        self.assertTrue(account)
        self.assertEqual(set(lines.account_id.ids), set(account.ids))
        # October is closed: what is still on the VAT accounts
        self.assertAlmostEqual(by_date[date(2026, 12, 12)], october_tax)
        # November: booked + October's average for the remaining 21/30 days
        self.assertAlmostEqual(
            by_date[date(2027, 1, 12)],
            november_tax + october_tax * 21 / 30,
            places=2,
        )
        # December: the estimate; January is due after the horizon
        self.assertAlmostEqual(by_date[date(2027, 2, 12)], october_tax)
        self.assertEqual(len(lines), 3)

    def test_payment_term_split(self):
        term = self.env.ref("account.account_payment_term_30days")
        split = self.Line._cash_flow_split_by_terms(
            term, date(2026, 11, 10), 100.0, self.company
        )
        self.assertEqual(split, [(date(2026, 12, 10), 100.0)])
        split = self.Line._cash_flow_split_by_terms(
            False, date(2026, 11, 10), -50.0, self.company
        )
        self.assertEqual(split, [(date(2026, 11, 10), -50.0)])

    def test_settings_constraints(self):
        with self.assertRaises(ValidationError):
            self.company.cash_flow_vat_due_day = 32
        with self.assertRaises(ValidationError):
            self.company.cash_flow_horizon_months = 0
        with self.assertRaises(ValidationError):
            self.rule.history_months = 0

    def test_open_origin(self):
        line = self.Line.create(
            {
                "date": date.today() + relativedelta(days=1),
                "account_id": self.payable.id,
                "name": "Origin",
                "balance": -1.0,
                "company_id": self.company.id,
                "res_model": self.rule._name,
                "res_id": self.rule.id,
            }
        )
        action = line.action_open_origin()
        self.assertEqual(action["res_id"], self.rule.id)
        self.assertFalse(self.manual.action_open_origin())

    def test_cron_and_button(self):
        self.Line._cron_generate_auto_lines()
        action = self.Line.with_user(self.env.user).action_generate_auto_lines()
        self.assertEqual(action["tag"], "reload")
