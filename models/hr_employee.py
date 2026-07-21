# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    cr_identification_type = fields.Selection([
        ("01", "Cédula física"),
        ("03", "DIMEX"),
        ("04", "NITE"),
    ], string="Tipo de identificación CR")
    cr_tax_children = fields.Integer(string="Hijos para crédito fiscal", default=0)
    cr_tax_spouse = fields.Boolean(string="Crédito fiscal por cónyuge")
    cr_social_security_number = fields.Char(string="Número de asegurado CCSS")
    cr_bmc_exempt = fields.Boolean(string="Excepción de base mínima contributiva", help="Active únicamente con respaldo de la condición reportada ante SICERE.")
    cr_bmc_exempt_reason = fields.Char(string="Motivo de excepción BMC")

    @api.constrains("cr_tax_children")
    def _check_cr_tax_children(self):
        for employee in self:
            if employee.cr_tax_children < 0:
                raise ValidationError("La cantidad de hijos para crédito fiscal no puede ser negativa.")
