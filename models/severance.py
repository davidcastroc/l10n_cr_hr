# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrPayrollTermination(models.Model):
    _name = "cr.payroll.termination"
    _description = "Liquidación laboral Costa Rica"
    _order = "termination_date desc, id desc"

    name = fields.Char(required=True, default="Liquidación")
    employee_id = fields.Many2one("hr.employee", required=True)
    contract_id = fields.Many2one("hr.contract", required=True, domain="[('employee_id', '=', employee_id)]")
    company_id = fields.Many2one(related="employee_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    termination_date = fields.Date(required=True, default=fields.Date.context_today)
    reason = fields.Selection([
        ("resignation", "Renuncia"), ("dismissal_with_liability", "Despido con responsabilidad"),
        ("dismissal_without_liability", "Despido sin responsabilidad"),
        ("mutual", "Mutuo acuerdo"), ("contract_end", "Finalización de contrato"),
        ("death", "Fallecimiento"), ("other", "Otro")
    ], required=True)
    include_notice = fields.Boolean(string="Incluir preaviso")
    include_severance = fields.Boolean(string="Incluir cesantía")
    pending_salary = fields.Monetary()
    pending_commissions = fields.Monetary()
    pending_overtime = fields.Monetary()
    vacation_days = fields.Float()
    vacation_amount = fields.Monetary(compute="_compute_amounts", store=True, readonly=False)
    aguinaldo_amount = fields.Monetary(compute="_compute_amounts", store=True, readonly=False)
    notice_amount = fields.Monetary()
    severance_amount = fields.Monetary()
    other_income = fields.Monetary()
    deductions = fields.Monetary()
    gross_total = fields.Monetary(compute="_compute_totals", store=True)
    net_total = fields.Monetary(compute="_compute_totals", store=True)
    state = fields.Selection([("draft", "Borrador"), ("review", "En revisión"), ("approved", "Aprobada"), ("paid", "Pagada"), ("cancel", "Cancelada")], default="draft")
    notes = fields.Text()

    @api.depends("contract_id.wage", "vacation_days", "employee_id", "termination_date")
    def _compute_amounts(self):
        Payslip = self.env["hr.payslip"]
        for rec in self:
            wage = rec.contract_id.wage or 0.0
            divisor = rec.contract_id.cr_days_divisor or 30.0
            rec.vacation_amount = rec.vacation_days * wage / divisor
            # La cifra final debe validarse: esta estimación reutiliza la misma base histórica de aguinaldo.
            dummy = Payslip.new({
                "employee_id": rec.employee_id.id,
                "contract_id": rec.contract_id.id,
                "company_id": rec.company_id.id,
                "date_from": rec.termination_date,
                "date_to": rec.termination_date,
            })
            rec.aguinaldo_amount = dummy._cr_compute_aguinaldo() if rec.employee_id and rec.termination_date else 0.0

    @api.depends("pending_salary", "pending_commissions", "pending_overtime", "vacation_amount", "aguinaldo_amount", "notice_amount", "severance_amount", "other_income", "deductions")
    def _compute_totals(self):
        for rec in self:
            rec.gross_total = sum([
                rec.pending_salary, rec.pending_commissions, rec.pending_overtime,
                rec.vacation_amount, rec.aguinaldo_amount,
                rec.notice_amount if rec.include_notice else 0.0,
                rec.severance_amount if rec.include_severance else 0.0,
                rec.other_income,
            ])
            rec.net_total = rec.gross_total - rec.deductions

    @api.constrains("termination_date", "contract_id")
    def _check_date(self):
        for rec in self:
            if rec.contract_id.date_start and rec.termination_date < rec.contract_id.date_start:
                raise ValidationError("La terminación no puede ser anterior al inicio del contrato.")
