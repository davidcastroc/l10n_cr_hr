# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrPayrollDeduction(models.Model):
    _name = "cr.payroll.deduction"
    _description = "Deducción recurrente de nómina CR"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority, employee_id, date_from, id"

    name = fields.Char(required=True, tracking=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
    deduction_type = fields.Selection([
        ("alimony", "Pensión alimentaria"),
        ("garnishment", "Embargo"),
        ("popular_loan", "Crédito Banco Popular"),
        ("loan", "Préstamo interno"),
        ("advance", "Adelanto salarial"),
        ("solidarity", "Asociación solidarista"),
        ("cooperative", "Cooperativa"),
        ("savings", "Ahorro"),
        ("insurance", "Seguro"),
        ("other", "Otra"),
    ], required=True, tracking=True)
    calculation = fields.Selection([("fixed", "Monto fijo"), ("percent", "Porcentaje")], default="fixed", required=True)
    amount = fields.Monetary(currency_field="currency_id", tracking=True)
    percentage = fields.Float(digits=(8, 5), tracking=True)
    original_amount = fields.Monetary(currency_field="currency_id")
    balance = fields.Monetary(currency_field="currency_id", tracking=True)
    currency_id = fields.Many2one("res.currency", related="employee_id.company_id.currency_id", store=True)
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(tracking=True)
    priority = fields.Integer(default=50)
    court_file = fields.Char(string="Expediente / referencia")
    beneficiary = fields.Char(string="Beneficiario / acreedor")
    active = fields.Boolean(default=True, tracking=True)
    notes = fields.Text()
    movement_ids = fields.One2many("cr.payroll.deduction.movement", "deduction_id", string="Movimientos")

    @api.constrains("amount", "percentage", "balance", "date_from", "date_to")
    def _check_amounts(self):
        for rec in self:
            if rec.amount < 0 or rec.percentage < 0 or rec.balance < 0:
                raise ValidationError("Los montos y porcentajes no pueden ser negativos.")
            if rec.percentage > 100:
                raise ValidationError("El porcentaje no puede superar cien.")
            if rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError("La fecha final no puede ser anterior a la inicial.")

    def amount_for_period(self, base):
        self.ensure_one()
        amount = self.amount if self.calculation == "fixed" else base * self.percentage / 100.0
        if self.original_amount or self.balance:
            amount = min(amount, self.balance)
        return max(amount, 0.0)
