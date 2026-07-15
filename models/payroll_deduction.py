# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class CrPayrollDeduction(models.Model):
    _name = "cr.payroll.deduction"
    _description = "Deducción recurrente de nómina CR"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority, employee_id, date_from"

    name = fields.Char(string="Descripción", required=True, tracking=True)
    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True, index=True, tracking=True)
    deduction_type = fields.Selection([
        ("alimony", "Pensión alimentaria"), ("garnishment", "Embargo"),
        ("loan", "Préstamo"), ("advance", "Adelanto"),
        ("solidarity", "Asociación solidarista"), ("cooperative", "Cooperativa"),
        ("savings", "Ahorro"), ("insurance", "Seguro"), ("other", "Otra"),
    ], string="Tipo de deducción", required=True, tracking=True)
    calculation = fields.Selection([("fixed", "Monto fijo"), ("percent", "Porcentaje")], string="Forma de cálculo", default="fixed", required=True)
    amount = fields.Monetary(string="Cuota o monto", currency_field="currency_id", tracking=True)
    percentage = fields.Float(string="Porcentaje", digits=(8, 5), tracking=True)
    original_amount = fields.Monetary(string="Monto original", currency_field="currency_id")
    balance = fields.Monetary(string="Saldo pendiente", currency_field="currency_id", tracking=True)
    currency_id = fields.Many2one("res.currency", related="employee_id.company_id.currency_id", store=True)
    date_from = fields.Date(string="Vigente desde", required=True, tracking=True)
    date_to = fields.Date(string="Vigente hasta", tracking=True)
    priority = fields.Integer(string="Prioridad", default=50)
    frequency = fields.Selection([("weekly", "Semanal"), ("biweekly", "Quincenal"), ("monthly", "Mensual"), ("each", "Cada recibo")], string="Frecuencia", default="each")
    court_file = fields.Char(string="Expediente / referencia")
    beneficiary = fields.Char(string="Beneficiario")
    active = fields.Boolean(default=True, tracking=True)
    notes = fields.Text(string="Observaciones")

    @api.constrains("amount", "percentage", "balance")
    def _check_amounts(self):
        for rec in self:
            if rec.amount < 0 or rec.percentage < 0 or rec.balance < 0:
                raise ValidationError("Los montos y porcentajes no pueden ser negativos.")

    def amount_for_period(self, base):
        self.ensure_one()
        amount = self.amount if self.calculation == "fixed" else base * self.percentage / 100.0
        if self.balance:
            amount = min(amount, self.balance)
        return max(amount, 0.0)
