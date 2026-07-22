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
        ("alimony", "Pensión alimentaria"),
        ("garnishment", "Embargo salarial"),
        ("popular_credit", "Crédito Banco Popular"),
        ("loan", "Préstamo interno"),
        ("advance", "Adelanto salarial"),
        ("solidarity", "Asociación solidarista"),
        ("cooperative", "Cooperativa"),
        ("savings", "Ahorro"),
        ("insurance", "Seguro"),
        ("other", "Otra deducción"),
    ], string="Tipo de deducción", required=True, tracking=True)
    calculation = fields.Selection(
        [("fixed", "Monto fijo"), ("percent", "Porcentaje")],
        string="Forma de cálculo", default="fixed", required=True
    )
    amount = fields.Monetary(string="Cuota o monto", currency_field="currency_id", tracking=True)
    percentage = fields.Float(string="Porcentaje", digits=(8, 5), tracking=True)
    original_amount = fields.Monetary(string="Monto original", currency_field="currency_id")
    balance = fields.Monetary(string="Saldo pendiente", currency_field="currency_id", tracking=True)
    currency_id = fields.Many2one("res.currency", related="employee_id.company_id.currency_id", store=True)
    date_from = fields.Date(string="Vigente desde", required=True, tracking=True)
    date_to = fields.Date(string="Vigente hasta", tracking=True)
    priority = fields.Integer(string="Prioridad", default=50)
    frequency = fields.Selection([
        ("weekly", "Semanal"),
        ("biweekly", "Quincenal"),
        ("monthly", "Mensual"),
        ("each", "Cada recibo"),
    ], string="Frecuencia", default="each", required=True)
    court_file = fields.Char(string="Expediente / referencia")
    beneficiary = fields.Char(string="Beneficiario")
    active = fields.Boolean(default=True, tracking=True)
    notes = fields.Text(string="Observaciones")
    movement_ids = fields.One2many(
        "cr.payroll.deduction.movement", "deduction_id", string="Movimientos", readonly=True
    )

    @api.constrains("amount", "percentage", "balance", "original_amount")
    def _check_amounts(self):
        for rec in self:
            if any(value < 0 for value in (rec.amount, rec.percentage, rec.balance, rec.original_amount)):
                raise ValidationError("Los montos, porcentajes y saldos no pueden ser negativos.")
            if rec.calculation == "fixed" and not rec.amount:
                raise ValidationError("Una deducción fija debe tener una cuota mayor que cero.")
            if rec.calculation == "percent" and rec.percentage > 100:
                raise ValidationError("El porcentaje de deducción no puede superar el 100 %.")

    @api.onchange("original_amount")
    def _onchange_original_amount(self):
        if self.original_amount and not self.balance:
            self.balance = self.original_amount

    def applies_to_payslip(self, payslip):
        self.ensure_one()
        if self.frequency == "each":
            return True
        if self.frequency == "weekly":
            return payslip.contract_id.cr_pay_frequency == "weekly"
        if self.frequency == "biweekly":
            return payslip.contract_id.cr_pay_frequency == "biweekly"
        if self.frequency == "monthly":
            month_start = payslip.date_to.replace(day=1)
            already = self.env["cr.payroll.deduction.movement"].search_count([
                ("deduction_id", "=", self.id),
                ("state", "=", "applied"),
                ("date", ">=", month_start),
                ("date", "<=", payslip.date_to),
                ("payslip_id", "!=", payslip.id),
            ])
            return not already
        return True

    def amount_for_period(self, base, payslip=None):
        self.ensure_one()
        if payslip and not self.applies_to_payslip(payslip):
            return 0.0
        amount = self.amount if self.calculation == "fixed" else base * self.percentage / 100.0
        if self.balance:
            amount = min(amount, self.balance)
        return max(amount, 0.0)
