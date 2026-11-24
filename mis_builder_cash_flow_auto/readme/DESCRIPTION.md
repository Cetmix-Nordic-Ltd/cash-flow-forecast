Generates the forecast lines of the OCA *MIS Builder Cash Flow* report
(`mis_builder_cash_flow`) automatically, so that the report shows the
expected payments that are not yet open invoices or bills.

The module adds two sources:

- **Recurring costs and income**: rules that forecast for example wages
  or rent as the monthly average of chosen accounts over the past
  months.
- **VAT**: the VAT payment of each VAT period, due on the due date of
  the period. A period that has ended is forecast with the VAT still on
  the VAT accounts; the current and future periods use the average of
  past periods.

Other modules add more sources:

| Module | Source |
|---|---|
| `mis_builder_cash_flow_auto_sale` | Confirmed sales orders not yet invoiced |
| `mis_builder_cash_flow_auto_purchase` | Purchase orders not yet billed |
| `mis_builder_cash_flow_auto_contract` | Future invoices of OCA contracts |

The generated lines are updated every day and on request. Forecast lines
entered by hand are never changed.
