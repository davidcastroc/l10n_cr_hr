# -*- coding: utf-8 -*-
from calendar import monthrange
from odoo import api, fields, models


class HrContract(models.Model):
    _inherit = "hr.contract"

    cr_pay_frequency = fields.Selection([
        ("weekly", "Semanal"),
        ("biweekly", "Quincenal"),
        ("monthly", "Mensual"),
        ("hourly", "Por hora"),
        ("daily", "Por día"),
    ], default="monthly", required=True, string="Frecuencia de pago")
    cr_journey_type = fields.Selection([
        ("day", "Diurna"),
        ("mixed", "Mixta"),
        ("night", "Nocturna"),
        ("partial", "Medio tiempo / parcial"),
        ("rotating", "Rotativa"),
        ("route", "Ruta"),
    ], default="day", string="Tipo de jornada")
    cr_saturday_scheme = fields.Selection([
        ("none", "No labora sábados"),
        ("all", "Todos los sábados"),
        ("first", "Primer sábado del mes"),
        ("last_two", "Dos últimos sábados del mes"),
        ("route", "Según ruta autorizada"),
    ], default="none", string="Esquema de sábados")
    cr_salary_mode = fields.Selection([
        ("fixed", "Salario fijo"),
        ("hourly", "Por hora"),
        ("daily", "Por día"),
        ("mixed", "Mixto"),
    ], default="fixed", string="Modalidad salarial")
    cr_hours_per_day = fields.Float(string="Horas ordinarias por día", default=8.0)
    cr_expected_hours_week = fields.Float(string="Horas ordinarias por semana", default=48.0)
    cr_days_divisor = fields.Float(string="Divisor de salario diario", default=30.0)
    cr_allow_advanced_leave = fields.Boolean(string="Permitir vacaciones adelantadas")

    def cr_period_is_valid(self, date_from, date_to):
        self.ensure_one()
        if not date_from or not date_to or date_from > date_to:
            return False
        if self.cr_pay_frequency == "biweekly":
            last_day = monthrange(date_to.year, date_to.month)[1]
            return (
                date_from.year == date_to.year
                and date_from.month == date_to.month
                and ((date_from.day == 1 and date_to.day == 15) or (date_from.day == 16 and date_to.day == last_day))
            )
        if self.cr_pay_frequency == "monthly":
            return date_from.day == 1 and date_to.day == monthrange(date_to.year, date_to.month)[1]
        if self.cr_pay_frequency == "weekly":
            return (date_to - date_from).days == 6
        return True

    @api.onchange("cr_pay_frequency")
    def _onchange_cr_pay_frequency(self):
        if self.cr_pay_frequency == "hourly":
            self.cr_salary_mode = "hourly"
