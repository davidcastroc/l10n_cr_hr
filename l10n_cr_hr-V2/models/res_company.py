# -*- coding: utf-8 -*-
from odoo import fields, models

class ResCompany(models.Model):
    _inherit = "res.company"

    cr_payroll_rounding = fields.Selection([("cent", "Dos decimales"), ("colon", "Colón más cercano")], default="colon")
    cr_legal_bonus = fields.Boolean(string="Aguinaldo legal CR", default=True)
    cr_allow_bonus_adjustments = fields.Boolean(string="Permitir ajustes de aguinaldo", default=True)
    cr_school_salary = fields.Boolean(string="Salario escolar", default=False)
    cr_overtime_requires_approval = fields.Boolean(default=True)

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cr_payroll_rounding = fields.Selection(related="company_id.cr_payroll_rounding", readonly=False)
    cr_legal_bonus = fields.Boolean(related="company_id.cr_legal_bonus", readonly=False)
    cr_allow_bonus_adjustments = fields.Boolean(related="company_id.cr_allow_bonus_adjustments", readonly=False)
    cr_school_salary = fields.Boolean(related="company_id.cr_school_salary", readonly=False)
    cr_overtime_requires_approval = fields.Boolean(related="company_id.cr_overtime_requires_approval", readonly=False)
