# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrPayrollDisabilityRule(models.Model):
    _name = "cr.payroll.disability.rule"
    _description = "Regla de incapacidad de Costa Rica"
    _order = "code, day_from, date_from desc"

    name = fields.Char(
        string="Nombre",
        required=True,
    )

    code = fields.Char(
        string="Código",
        required=True,
        index=True,
    )

    leave_type_id = fields.Many2one(
        comodel_name="hr.leave.type",
        string="Tipo de ausencia",
        ondelete="restrict",
    )

    day_from = fields.Integer(
        string="Desde el día",
        required=True,
        default=1,
    )

    day_to = fields.Integer(
        string="Hasta el día",
        help="Vacío o cero significa sin límite.",
    )

    deduction_rate = fields.Float(
        string="Porcentaje de rebajo",
        default=100.0,
        help=(
            "Porcentaje del salario ordinario correspondiente al período "
            "de incapacidad o licencia que debe rebajarse."
        ),
    )

    employer_rate = fields.Float(
        string="Porcentaje patronal",
        default=0.0,
        help="Porcentaje cubierto directamente por el patrono.",
    )

    subsidy_rate = fields.Float(
        string="Porcentaje de subsidio",
        default=0.0,
        help="Porcentaje cubierto por la institución correspondiente.",
    )

    subsidy_paid_in_payroll = fields.Boolean(
        string="Adelantar subsidio en planilla",
        default=False,
        help=(
            "Active esta opción cuando la empresa adelante al empleado "
            "el subsidio institucional y posteriormente gestione su recuperación."
        ),
    )

    employer_payment_taxable = fields.Boolean(
        string="Pago patronal sujeto a cargas sociales",
        default=False,
        help=(
            "Indica si el pago realizado por el patrono durante la incapacidad "
            "forma parte de la base para cargas sociales."
        ),
    )

    employer_payment_taxable_income = fields.Boolean(
        string="Pago patronal sujeto a renta",
        default=False,
        help=(
            "Indica si el pago patronal se considera ingreso sujeto "
            "al impuesto sobre la renta."
        ),
    )

    affects_social_security = fields.Boolean(
        string="Afecta cargas sociales",
        default=False,
    )

    affects_income_tax = fields.Boolean(
        string="Afecta impuesto sobre la renta",
        default=False,
    )

    affects_aguinaldo = fields.Boolean(
        string="Afecta aguinaldo",
        default=False,
    )

    affects_vacation = fields.Boolean(
        string="Afecta vacaciones",
        default=False,
    )

    date_from = fields.Date(
        string="Vigente desde",
        required=True,
    )

    date_to = fields.Date(
        string="Vigente hasta",
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        help="Vacío significa que la regla aplica a nivel nacional.",
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
    )

    source = fields.Char(
        string="Fuente legal",
    )

    notes = fields.Text(
        string="Observaciones",
    )

    @api.constrains(
        "day_from",
        "day_to",
        "deduction_rate",
        "employer_rate",
        "subsidy_rate",
        "date_from",
        "date_to",
    )
    def _check_rule(self):
        for record in self:
            if record.day_from < 1:
                raise ValidationError(
                    "El día inicial debe ser mayor o igual a uno."
                )

            if record.day_to and record.day_to < record.day_from:
                raise ValidationError(
                    "El día final no puede ser menor que el día inicial."
                )

            percentages = {
                "porcentaje de rebajo": record.deduction_rate,
                "porcentaje patronal": record.employer_rate,
                "porcentaje de subsidio": record.subsidy_rate,
            }

            for label, percentage in percentages.items():
                if percentage < 0.0 or percentage > 100.0:
                    raise ValidationError(
                        f"El {label} debe estar entre cero y cien."
                    )

            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(
                    "La fecha de vigencia final no puede ser anterior "
                    "a la fecha inicial."
                )