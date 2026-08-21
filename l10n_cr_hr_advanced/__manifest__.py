# -*- coding: utf-8 -*-
{
    "name": "RH Costa Rica - Nómina Avanzada",
    "summary": "Retroactivos, eventos tardíos, liquidaciones negociadas y auditoría avanzada para Nómina Costa Rica",
    "version": "18.0.5.0.0",
    "category": "Human Resources/Payroll",
    "author": "Castro Li",
    "website": "https://castrolicr.com",
    "license": "LGPL-3",
    "depends": [
        "l10n_cr_hr",
        "hr_payroll",
        "hr_holidays",
        "hr_attendance",
        "account",
        "mail"
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/retroactive_policy_views.xml",
        "views/retroactive_views.xml",
        "views/late_leave_event_views.xml",
        "views/attendance_correction_views.xml",
        "views/severance_advanced_views.xml",
        "views/menu_views.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
