# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import fields, models


class MisCashFlowForecastLine(models.Model):
    _inherit = "mis.cash_flow.forecast_line"

    source = fields.Selection(
        selection_add=[("contract", "Contract")],
        ondelete={"contract": "cascade"},
    )

    def _get_auto_line_values(self, company, date_from, date_to):
        values = super()._get_auto_line_values(company, date_from, date_to)
        return values + self._get_contract_forecast_values(company, date_from, date_to)

    def _get_contract_forecast_values(self, company, date_from, date_to):
        """One invoice per contract and invoice date, paid by the
        contract's payment terms: money in for sale contracts, out for
        purchase contracts."""
        lines = self.env["contract.line"].search(
            [
                ("contract_id.company_id", "=", company.id),
                ("contract_id.active", "=", True),
                ("is_canceled", "=", False),
                ("display_type", "=", False),
                ("recurring_next_date", "!=", False),
                ("recurring_next_date", "<=", date_to),
            ]
        )
        by_invoice = defaultdict(float)
        for line in lines:
            amount = line._get_cash_flow_amount()
            for invoice_date in line._get_cash_flow_invoice_dates(date_to):
                by_invoice[(line.contract_id, max(invoice_date, date_from))] += amount
        values = []
        for (contract, invoice_date), amount in by_invoice.items():
            amount = contract.currency_id._convert(
                amount, company.currency_id, company, date_from
            )
            if company.currency_id.is_zero(amount):
                continue
            partner = (
                contract.invoice_partner_id or contract.partner_id
            ).commercial_partner_id.with_company(company)
            if contract.contract_type == "purchase":
                amount = -amount
                account = partner.property_account_payable_id
                term = (
                    contract.payment_term_id
                    or partner.property_supplier_payment_term_id
                )
            else:
                account = partner.property_account_receivable_id
                term = contract.payment_term_id or partner.property_payment_term_id
            for due, part in self._cash_flow_split_by_terms(
                term, invoice_date, amount, company
            ):
                values.append(
                    {
                        "date": max(due, date_from),
                        "account_id": account.id,
                        "partner_id": partner.id,
                        "name": contract.name,
                        "balance": part,
                        "source": "contract",
                        "res_model": contract._name,
                        "res_id": contract.id,
                    }
                )
        return values
