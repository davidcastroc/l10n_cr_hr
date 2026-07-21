# -*- coding: utf-8 -*-
from odoo import fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    cr_payroll_treatment = fields.Selection([
        ("vacation", "Vacaciones pagadas"),
        ("paid", "Permiso con goce"),
        ("unpaid", "Permiso sin goce"),
        ("ccss", "Incapacidad CCSS"),
        ("ins", "Incapacidad INS"),
        ("maternity", "Licencia de maternidad"),
        ("paternity", "Licencia de paternidad"),
        ("breastfeeding", "Lactancia"),
    ], string="Tratamiento de nómina CR")
