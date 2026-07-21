# -*- coding: utf-8 -*-
from odoo import fields, models


class CrPayrollDeductionMovement(models.Model):
    _name = "cr.payroll.deduction.movement"
    _description = "Movimiento de deducción de nómina CR"
    _order = "date desc, id desc"

    deduction_id = fields.Many2one("cr.payroll.deduction", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one(related="deduction_id.employee_id", store=True)
    payslip_id = fields.Many2one("hr.payslip", required=True, ondelete="cascade", index=True)
    date = fields.Date(related="payslip_id.date_to", store=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="deduction_id.currency_id", store=True)
    state = fields.Selection([("applied", "Aplicado"), ("reversed", "Revertido")], default="applied", required=True)

    _sql_constraints = [
        ("deduction_payslip_unique", "unique(deduction_id,payslip_id)", "La deducción ya fue aplicada en este recibo."),
    ]
