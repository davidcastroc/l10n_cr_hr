# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrPayrollIncident(models.Model):
    _name = "cr.payroll.incident"
    _description = "Incidencia de nómina Costa Rica"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(required=True, default="Nueva incidencia", tracking=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
    contract_id = fields.Many2one("hr.contract", domain="[('employee_id', '=', employee_id)]")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    incident_type = fields.Selection([
        ("commission", "Comisión"), ("bonus", "Bono"), ("incentive", "Incentivo"),
        ("productivity", "Productividad"), ("availability", "Disponibilidad / guardia"),
        ("overtime_15", "Hora extra 1.5"), ("holiday_work", "Horas trabajadas en feriado"),
        ("holiday_overtime", "Hora extra en feriado / pago triple"),
        ("unpaid_hours", "Horas no laboradas"), ("unpaid_days", "Días no laborados"),
        ("tardiness", "Tardías"), ("retroactive", "Retroactivo"),
        ("salary_difference", "Diferencia salarial"), ("vacation_pay", "Ajuste de vacaciones"),
        ("other_income", "Otro ingreso salarial"), ("reimbursement", "Reembolso no salarial"),
        ("other_deduction", "Otra deducción"), ("aguinaldo_adjustment", "Ajuste de aguinaldo"),
    ], required=True, index=True, tracking=True)
    quantity = fields.Float(default=1.0)
    rate = fields.Float(string="Tarifa / valor unitario")
    amount = fields.Monetary(compute="_compute_amount", store=True, readonly=False)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    description = fields.Text()
    state = fields.Selection([
        ("draft", "Borrador"), ("submitted", "Enviado"), ("approved", "Aprobado"),
        ("applied", "Aplicado"), ("rejected", "Rechazado"), ("cancel", "Cancelado"),
    ], default="draft", required=True, index=True, tracking=True)
    payslip_id = fields.Many2one("hr.payslip", readonly=True, copy=False)
    attachment_ids = fields.Many2many("ir.attachment", string="Adjuntos")

    @api.depends("quantity", "rate")
    def _compute_amount(self):
        for rec in self:
            if rec.quantity and rec.rate:
                rec.amount = rec.quantity * rec.rate

    @api.constrains("quantity", "rate", "amount")
    def _check_values(self):
        for rec in self:
            if rec.quantity < 0 or rec.rate < 0:
                raise ValidationError("La cantidad y la tarifa no pueden ser negativas.")
            if rec.amount < 0 and rec.incident_type != "aguinaldo_adjustment":
                raise ValidationError("Solo el ajuste de aguinaldo puede ser negativo.")

    def action_submit(self): self.write({"state": "submitted"})
    def action_approve(self): self.write({"state": "approved"})
    def action_reject(self): self.write({"state": "rejected"})
    def action_cancel(self): self.write({"state": "cancel"})
