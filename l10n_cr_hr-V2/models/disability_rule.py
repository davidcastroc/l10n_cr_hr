# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrPayrollDisabilityRule(models.Model):
    _name = "cr.payroll.disability.rule"
    _description = "Regla de incapacidad y licencia de Costa Rica"
    _order = "code, day_from, company_id"

    name = fields.Char(string="Nombre", required=True)
    code = fields.Selection(
        [
            ("CCSS", "Incapacidad CCSS"),
            ("INS", "Incapacidad INS"),
            ("MATERNITY", "Licencia de maternidad"),
            ("PATERNITY", "Licencia de paternidad"),
        ],
        string="Tipo de regla",
        required=True,
        index=True,
    )
    leave_type_id = fields.Many2one("hr.leave.type", string="Tipo de ausencia")
    day_from = fields.Integer(string="Desde el día", required=True, default=1)
    day_to = fields.Integer(string="Hasta el día", help="Vacío o cero significa sin límite")
    deduction_rate = fields.Float(
        string="Porcentaje a rebajar del salario ordinario",
        default=100.0,
        help="Normalmente se rebaja el 100 % del valor ordinario de los días de ausencia y luego se agregan por separado la parte patronal y, si corresponde, el subsidio adelantado.",
    )
    employer_rate = fields.Float(string="Porcentaje pagado por el patrono")
    subsidy_rate = fields.Float(string="Porcentaje cubierto por la institución")
    subsidy_paid_in_payroll = fields.Boolean(
        string="Adelantar subsidio en planilla",
        help="Active solo cuando la empresa paga al colaborador el subsidio y posteriormente lo recupera de la CCSS o del INS.",
    )
    employer_payment_taxable = fields.Boolean(
        string="Pago patronal sujeto a cargas sociales",
        default=False,
    )
    employer_payment_taxable_income = fields.Boolean(
        string="Pago patronal sujeto a renta",
        default=False,
    )
    affects_aguinaldo = fields.Boolean(string="Pago patronal afecta aguinaldo", default=False)
    affects_vacation = fields.Boolean(string="Pago patronal afecta vacaciones", default=False)
    date_from = fields.Date(string="Vigente desde", required=True)
    date_to = fields.Date(string="Vigente hasta")
    company_id = fields.Many2one("res.company", string="Compañía", help="Vacío significa regla nacional")
    active = fields.Boolean(string="Activo", default=True)
    source = fields.Char(string="Fuente legal")
    notes = fields.Text(string="Observaciones")

    @api.constrains(
        "day_from", "day_to", "deduction_rate", "employer_rate", "subsidy_rate", "date_from", "date_to"
    )
    def _check_rule(self):
        for rec in self:
            if rec.day_from < 1 or (rec.day_to and rec.day_to < rec.day_from):
                raise ValidationError("Rango de días inválido.")
            for value in (rec.deduction_rate, rec.employer_rate, rec.subsidy_rate):
                if not 0 <= value <= 100:
                    raise ValidationError("Los porcentajes deben estar entre cero y cien.")
            if rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError("La vigencia final no puede ser anterior a la inicial.")
            if rec.employer_rate + rec.subsidy_rate > 100.0001:
                raise ValidationError("La suma patrono + subsidio no puede superar el 100 %.")
