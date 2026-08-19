# -*- coding: utf-8 -*-
{
    "name": "RH Costa Rica - Asistencias y Reposiciones",
    "summary": "Reposición aprobada de horas, marcaciones y segmentación avanzada de jornadas",
    "version": "18.0.3.0.0",
    "category": "Human Resources/Attendances",
    "author": "Castro Li",
    "website": "https://castrolicr.com",
    "license": "LGPL-3",
    "depends": ["l10n_cr_hr", "hr_attendance", "hr_payroll", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/hour_recovery_cron.xml",
        "views/hour_recovery_views.xml",
        "views/shift_segmentation_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
