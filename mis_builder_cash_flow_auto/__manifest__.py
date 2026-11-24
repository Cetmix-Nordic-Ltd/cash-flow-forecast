# Copyright 2026 Cetmix Nordic Ltd
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "MIS Builder Cash Flow Auto Forecast",
    "summary": "Generate cash flow forecast lines from recurring costs and VAT",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Cetmix Nordic Ltd",
    "website": "https://github.com/Cetmix-Nordic-Ltd/cash-flow-forecast",
    "category": "Accounting",
    "depends": [
        "account",
        "mis_builder_cash_flow",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/mis_cash_flow_recurring_rule_security.xml",
        "data/ir_cron_data.xml",
        "views/mis_cash_flow_forecast_line_views.xml",
        "views/mis_cash_flow_recurring_rule_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "demo": [
        "demo/mis_cash_flow_recurring_rule_demo.xml",
    ],
    "images": ["static/description/img/forecast_lines.png"],
    "installable": True,
}
