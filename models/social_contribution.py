# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class CrPayrollSocialContribution(models.Model):
    _name = "cr.payroll.social.contribution"
    _description = "Contribución social CR"
    _order = "sequence, code, date_from desc"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    side = fields.Selection([("employee", "Trabajador"), ("employer", "Patrono")], required=True)
    rate = fields.Float(required=True, digits=(8, 5), help="Porcentaje, por ejemplo 5.50")
    date_from = fields.Date(required=True)
    date_to = fields.Date()
    company_id = fields.Many2one("res.company", help="Vacío = nacional")
    affects_net = fields.Boolean(default=True)
    account_id = fields.Many2one("account.account")
    source = fields.Char()
    active = fields.Boolean(default=True)

    _sql_constraints = [("cr_social_uniq", "unique(code,date_from,company_id)", "Contribución duplicada para la vigencia.")]

    @api.constrains("rate")
    def _check_rate(self):
        for rec in self:
            if rec.rate < 0 or rec.rate > 100:
                raise ValidationError("La tasa debe estar entre 0 y 100.")

    @api.model
    def total_rate_at(self, side, on_date, company=None):
        company = company or self.env.company
        recs = self.search([
            ("side", "=", side), ("active", "=", True),
            ("date_from", "<=", on_date), "|", ("date_to", "=", False), ("date_to", ">=", on_date),
            "|", ("company_id", "=", company.id), ("company_id", "=", False),
        ])
        # Evita sumar dos vigencias del mismo código.
        selected = {}
        for rec in recs.sorted(lambda r: (bool(r.company_id), r.date_from), reverse=True):
            selected.setdefault(rec.code, rec)
        return sum(r.rate for r in selected.values())
