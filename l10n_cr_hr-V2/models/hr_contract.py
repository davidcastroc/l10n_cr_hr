# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrContract(models.Model):
    _inherit = "hr.contract"

    cr_pay_frequency = fields.Selection(
        selection=[
            ("weekly", "Semanal"),
            ("biweekly", "Quincenal"),
            ("monthly", "Mensual"),
            ("hourly", "Por hora"),
            ("daily", "Por día"),
        ],
        string="Frecuencia de pago",
        default="monthly",
        required=True,
        help="Periodicidad con la que se generan y pagan los recibos de nómina.",
    )

    cr_salary_mode = fields.Selection(
        selection=[
            ("fixed", "Salario fijo"),
            ("hourly", "Por hora"),
            ("daily", "Por día"),
            ("mixed", "Mixto"),
        ],
        string="Modalidad salarial",
        default="fixed",
        required=True,
        help="Forma utilizada para determinar el salario del colaborador.",
    )

    cr_journey_type = fields.Selection(
        selection=[
            ("day", "Diurna"),
            ("mixed", "Mixta"),
            ("night", "Nocturna"),
            ("partial", "Diurna medio tiempo"),
            ("rotating", "Rotativa"),
            ("route", "Ruta"),
        ],
        string="Tipo de jornada",
        default="day",
        required=True,
        help="Tipo de jornada laboral aplicable al contrato.",
    )

    cr_hours_per_day = fields.Float(
        string="Horas por día",
        default=8.0,
        required=True,
        help="Cantidad ordinaria de horas laboradas por día.",
    )

    cr_days_divisor = fields.Float(
        string="Divisor de salario diario",
        default=30.0,
        required=True,
        help=(
            "Divisor utilizado para obtener el salario diario a partir "
            "del salario mensual."
        ),
    )

    cr_allow_advanced_leave = fields.Boolean(
        string="Permitir vacaciones adelantadas",
        default=False,
        help=(
            "Permite asignar vacaciones aunque el colaborador todavía "
            "no tenga saldo acumulado suficiente."
        ),
    )

    @api.constrains("cr_hours_per_day")
    def _check_cr_hours_per_day(self):
        for contract in self:
            if contract.cr_hours_per_day <= 0:
                raise ValidationError(
                    _("Las horas por día deben ser mayores que cero.")
                )

            if contract.cr_hours_per_day > 24:
                raise ValidationError(
                    _("Las horas por día no pueden ser mayores que 24.")
                )

    @api.constrains("cr_days_divisor")
    def _check_cr_days_divisor(self):
        for contract in self:
            if contract.cr_days_divisor <= 0:
                raise ValidationError(
                    _("El divisor de salario diario debe ser mayor que cero.")
                )