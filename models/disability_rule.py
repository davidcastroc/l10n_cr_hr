# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrPayrollDisabilityRule(models.Model):
    _name = "cr.payroll.disability.rule"
    _description = "Regla de incapacidad de Costa Rica"
    _order = "code, day_from"

    name = fields.Char(string="Nombre", required=True)
    code = fields.Char(string="Código", required=True, index=True)
    leave_type_id = fields.Many2one("hr.leave.type", string="Tipo de ausencia")
    day_from = fields.Integer(string="Desde el día", required=True, default=1)
    day_to = fields.Integer(string="Hasta el día", help="Vacío o cero significa sin límite")
    employer_rate = fields.Float(string="Porcentaje patrono")
    subsidy_rate = fields.Float(string="Porcentaje de subsidio")
    affects_social_security = fields.Boolean(string="Afecta cargas sociales", default=False)
    affects_income_tax = fields.Boolean(string="Afecta impuesto sobre la renta", default=False)
    affects_aguinaldo = fields.Boolean(string="Afecta aguinaldo", default=False)
    affects_vacation = fields.Boolean(string="Afecta vacaciones", default=False)
    date_from = fields.Date(string="Vigente desde", required=True)
    date_to = fields.Date(string="Vigente hasta")
    company_id = fields.Many2one("res.company", string="Compañía", help="Vacío significa regla nacional")
    active = fields.Boolean(string="Activo", default=True)
    source = fields.Char(string="Fuente legal")
    notes = fields.Text(string="Observaciones")

    @api.constrains("day_from", "day_to", "employer_rate", "subsidy_rate", "date_from", "date_to")
    def _check_rule(self):
        for rec in self:
            if rec.day_from < 1 or (rec.day_to and rec.day_to < rec.day_from):
                raise ValidationError("Rango de días inválido.")
            if not 0 <= rec.employer_rate <= 100 or not 0 <= rec.subsidy_rate <= 100:
                raise ValidationError("Los porcentajes deben estar entre cero y cien.")
            if rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError("La vigencia final no puede ser anterior a la inicial.")
