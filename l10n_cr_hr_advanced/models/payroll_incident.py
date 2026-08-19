# -*- coding: utf-8 -*-
from odoo import fields, models


class CrPayrollIncident(models.Model):
    _inherit = "cr.payroll.incident"

    incident_type = fields.Selection(
        selection_add=[
            ("productivity", "Productividad"),
            ("availability", "Disponibilidad / guardia"),
            ("salary_difference", "Diferencia salarial"),
        ],
        ondelete={
            "productivity": "cascade",
            "availability": "cascade",
            "salary_difference": "cascade",
        },
    )
    retroactive_adjustment_id = fields.Many2one(
        "cr.payroll.retroactive.adjustment",
        string="Ajuste retroactivo origen",
        index=True,
        copy=False,
        ondelete="set null",
    )
    retroactive_origin_period = fields.Char(
        string="Período origen del retroactivo",
        copy=False,
    )
