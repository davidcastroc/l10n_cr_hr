# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class CrPayrollLegalParameter(models.Model):
    _name = "cr.payroll.legal.parameter"
    _description = "Parámetro legal de nómina CR"
    _order = "code, date_from desc"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    value = fields.Float(required=True, digits=(16, 6))
    date_from = fields.Date(required=True, index=True)
    date_to = fields.Date(index=True)
    company_id = fields.Many2one("res.company", index=True, help="Vacío = parámetro nacional")
    source = fields.Char()
    notes = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [("cr_param_uniq", "unique(code,date_from,company_id)", "Ya existe este parámetro para la fecha y empresa.")]

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError("La fecha final no puede ser anterior a la inicial.")

    @api.model
    def value_at(self, code, on_date, company=None, default=0.0):
        company = company or self.env.company
        rec = self.search([
            ("code", "=", code), ("active", "=", True),
            ("date_from", "<=", on_date), "|", ("date_to", "=", False), ("date_to", ">=", on_date),
            "|", ("company_id", "=", company.id), ("company_id", "=", False),
        ], order="company_id desc, date_from desc", limit=1)
        return rec.value if rec else default
