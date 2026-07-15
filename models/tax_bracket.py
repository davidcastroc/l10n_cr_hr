# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class CrPayrollTaxBracket(models.Model):
    _name = "cr.payroll.tax.bracket"
    _description = "Tramo de renta salarial CR"
    _order = "date_from desc, lower_bound"

    name = fields.Char(required=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date()
    lower_bound = fields.Monetary(required=True, currency_field="currency_id")
    upper_bound = fields.Monetary(currency_field="currency_id", help="Vacío = sin límite")
    rate = fields.Float(required=True, digits=(8, 5))
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.ref("base.CRC"))
    company_id = fields.Many2one("res.company", help="Vacío = nacional")
    source = fields.Char()
    active = fields.Boolean(default=True)

    @api.constrains("lower_bound", "upper_bound", "rate")
    def _check_values(self):
        for rec in self:
            if rec.upper_bound and rec.upper_bound <= rec.lower_bound:
                raise ValidationError("El límite superior debe ser mayor al inferior.")
            if rec.rate < 0 or rec.rate > 100:
                raise ValidationError("La tasa debe estar entre 0 y 100.")
