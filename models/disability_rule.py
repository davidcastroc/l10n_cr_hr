# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrPayrollDisabilityRule(models.Model):
    _name = "cr.payroll.disability.rule"
    _description = "Regla de incapacidad Costa Rica"
    _order = "code, day_from"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    leave_type_id = fields.Many2one("hr.leave.type")
    day_from = fields.Integer(required=True, default=1)
    day_to = fields.Integer(help="Vacío/0 significa sin límite")
    employer_rate = fields.Float(string="% patrono")
    subsidy_rate = fields.Float(string="% subsidio")
    affects_social_security = fields.Boolean(default=False)
    affects_income_tax = fields.Boolean(default=False)
    affects_aguinaldo = fields.Boolean(default=False)
    affects_vacation = fields.Boolean(default=False)
    date_from = fields.Date(required=True)
    date_to = fields.Date()
    company_id = fields.Many2one("res.company", help="Vacío = regla nacional")
    active = fields.Boolean(default=True)
    source = fields.Char()
    notes = fields.Text()

    @api.constrains("day_from", "day_to", "employer_rate", "subsidy_rate", "date_from", "date_to")
    def _check_rule(self):
        for rec in self:
            if rec.day_from < 1 or (rec.day_to and rec.day_to < rec.day_from):
                raise ValidationError("Rango de días inválido.")
            if not 0 <= rec.employer_rate <= 100 or not 0 <= rec.subsidy_rate <= 100:
                raise ValidationError("Los porcentajes deben estar entre 0 y 100.")
            if rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError("La vigencia final no puede ser anterior a la inicial.")
