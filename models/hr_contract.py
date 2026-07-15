# -*- coding: utf-8 -*-
from odoo import fields, models

class HrContract(models.Model):
    _inherit = "hr.contract"

    cr_pay_frequency = fields.Selection([
        ("weekly", "Semanal"), ("biweekly", "Quincenal"), ("monthly", "Mensual"),
        ("hourly", "Por hora"), ("daily", "Por día")], default="monthly", required=True)
    cr_journey_type = fields.Selection([
        ("day", "Diurna"), ("mixed", "Mixta"), ("night", "Nocturna"),
        ("partial", "Parcial"), ("rotating", "Rotativa"), ("route", "Ruta")], default="day")
    cr_salary_mode = fields.Selection([("fixed", "Fijo"), ("hourly", "Por hora"), ("daily", "Por día"), ("mixed", "Mixto")], default="fixed")
    cr_hours_per_day = fields.Float(default=8.0)
    cr_days_divisor = fields.Float(string="Divisor salario diario", default=30.0)
    cr_allow_advanced_leave = fields.Boolean(string="Permitir vacaciones adelantadas")
