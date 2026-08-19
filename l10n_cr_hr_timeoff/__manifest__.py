# -*- coding: utf-8 -*-
{
    "name": "RH Costa Rica - Ausencias y Eventos Tardíos",
    "summary": "Incapacidades tardías, restitución de vacaciones y trazabilidad contra nóminas cerradas",
    "version": "18.0.3.0.0",
    "category": "Human Resources/Time Off",
    "author": "Castro Li",
    "website": "https://castrolicr.com",
    "license": "LGPL-3",
    "depends": ["l10n_cr_hr", "hr_holidays", "hr_payroll", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "views/late_event_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
