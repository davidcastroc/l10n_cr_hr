# -*- coding: utf-8 -*-
from odoo import fields, models


class CrPayrollIncident(models.Model):
    _inherit = "cr.payroll.incident"

    incident_type = fields.Selection(
        selection_add=[
            ("unpaid_hours", "Horas no laboradas"),
            ("unpaid_days", "Días no laborados"),
            ("tardiness", "Tardía"),
        ],
        ondelete={
            "unpaid_hours": "cascade",
            "unpaid_days": "cascade",
            "tardiness": "cascade",
        },
    )
    hour_recovery_id = fields.Many2one(
        "cr.payroll.hour.recovery",
        string="Reposición de horas origen",
        index=True,
        copy=False,
        ondelete="set null",
    )
    shift_analysis_id = fields.Many2one(
        "cr.payroll.shift.analysis",
        string="Análisis de jornada origen",
        index=True,
        copy=False,
        ondelete="set null",
    )
    attendance_origin_period = fields.Char(
        string="Período origen de asistencia",
        copy=False,
    )
