# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrPayrollIncident(models.Model):
    _name = "cr.payroll.incident"
    _description = "Incidencia de nómina Costa Rica"
    _order = "date desc, id desc"

    name = fields.Char(string="Descripción", required=True, default="Nueva incidencia")
    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True, index=True)
    contract_id = fields.Many2one("hr.contract", string="Contrato", domain="[('employee_id', '=', employee_id)]")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today, index=True)
    incident_type = fields.Selection([
        ("commission", "Comisión"),
        ("bonus", "Bono"),
        ("incentive", "Incentivo"),
        ("overtime_15", "Hora extra 1.5"),
        ("holiday_work", "Feriado trabajado / pago doble"),
        ("holiday_overtime", "Hora extra en feriado / pago triple"),
        ("retroactive", "Retroactivo"),
        ("other_income", "Otro ingreso salarial"),
        ("reimbursement", "Reembolso no salarial"),
        ("other_deduction", "Otra deducción"),
        ("aguinaldo_adjustment", "Ajuste de aguinaldo"),
    ], string="Tipo de incidencia", required=True, index=True)
    quantity = fields.Float(string="Cantidad", default=1.0)
    rate = fields.Float(string="Tarifa / valor unitario")
    amount = fields.Monetary(string="Importe", compute="_compute_amount", store=True, readonly=False)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    description = fields.Text(string="Observaciones")
    state = fields.Selection([
        ("draft", "Borrador"), ("submitted", "Enviado"),
        ("approved", "Aprobado"), ("applied", "Aplicado"),
        ("rejected", "Rechazado"), ("cancel", "Cancelado")
    ], string="Estado", default="draft", required=True, index=True)
    payslip_id = fields.Many2one("hr.payslip", string="Recibo de nómina", readonly=True, copy=False)
    attachment_ids = fields.Many2many("ir.attachment", string="Adjuntos")

    @api.depends("quantity", "rate")
    def _compute_amount(self):
        for rec in self:
            if not rec.amount or rec.incident_type in {"overtime_15", "holiday_work", "holiday_overtime"}:
                rec.amount = rec.quantity * rec.rate

    @api.constrains("quantity", "rate", "amount")
    def _check_values(self):
        for rec in self:
            if rec.quantity < 0 or rec.rate < 0:
                raise ValidationError("La cantidad y la tarifa no pueden ser negativas.")
            if rec.amount < 0 and rec.incident_type != "aguinaldo_adjustment":
                raise ValidationError("Solo el ajuste de aguinaldo puede ser negativo.")

    def action_submit(self):
        self.write({"state": "submitted"})

    def action_approve(self):
        self.write({"state": "approved"})

    def action_reject(self):
        self.write({"state": "rejected"})

    def action_cancel(self):
        self.write({"state": "cancel"})
