# -*- coding: utf-8 -*-
from odoo import fields, models

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    cr_identification_type = fields.Selection([("01", "Cédula física"), ("02", "Cédula jurídica"), ("03", "DIMEX"), ("04", "NITE")], string="Tipo identificación CR")
    cr_tax_children = fields.Integer(string="Hijos para crédito fiscal", default=0)
    cr_tax_spouse = fields.Boolean(string="Crédito fiscal por cónyuge")
    cr_social_security_number = fields.Char(string="Número CCSS")
