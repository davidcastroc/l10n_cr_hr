# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class CrPayrollPublicHoliday(models.Model):
    _name = "cr.payroll.public.holiday"
    _description = "Feriado de Costa Rica"
    _order = "date"

    name = fields.Char(required=True)
    date = fields.Date(required=True, index=True)
    mandatory_pay = fields.Boolean(string="Pago obligatorio", default=True)
    holiday_type = fields.Selection([("fixed", "Fijo"), ("movable", "Móvil")], default="fixed", required=True)
    company_id = fields.Many2one("res.company", help="Vacío = nacional")
    source = fields.Char()
    notes = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [("cr_holiday_uniq", "unique(date,company_id)", "Ya existe un feriado en esa fecha para la empresa.")]
