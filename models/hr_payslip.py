# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import api, fields, models
from odoo.exceptions import UserError

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    cr_validation_message = fields.Text(compute="_compute_cr_validation_message")
    cr_incident_ids = fields.One2many("cr.payroll.incident", "payslip_id", string="Incidencias CR")

    def _compute_cr_validation_message(self):
        for slip in self:
            issues = []
            if not slip.contract_id:
                issues.append("Empleado sin contrato en el recibo.")
            elif slip.contract_id.wage <= 0:
                issues.append("El salario contractual debe ser mayor que cero.")
            if not slip.employee_id.identification_id:
                issues.append("Falta identificación del empleado.")
            if not slip.employee_id.bank_account_id:
                issues.append("Falta cuenta bancaria del empleado.")
            if slip.date_from and slip.date_to and slip.date_from > slip.date_to:
                issues.append("El período del recibo es inválido.")
            if slip.contract_id and not slip.contract_id.resource_calendar_id:
                issues.append("El contrato no tiene horario laboral.")
            if slip.employee_id and self.search_count([("id", "!=", slip.id), ("employee_id", "=", slip.employee_id.id), ("date_from", "=", slip.date_from), ("date_to", "=", slip.date_to), ("state", "in", ["done", "paid"]) ]):
                issues.append("Ya existe otro recibo finalizado para el mismo empleado y período.")
            slip.cr_validation_message = "\n".join(issues)

    def action_payslip_done(self):
        for slip in self:
            if slip.cr_validation_message:
                raise UserError("No se puede cerrar la nómina:\n%s" % slip.cr_validation_message)
        result = super().action_payslip_done()
        self._cr_apply_deduction_balances()
        self.mapped("cr_incident_ids").filtered(lambda x: x.state == "approved").write({"state": "applied"})
        return result

    def _cr_round(self, amount):
        self.ensure_one()
        return round(amount) if self.company_id.cr_payroll_rounding == "colon" else round(amount, 2)

    def _cr_input_amount(self, code):
        self.ensure_one()
        return sum(self.input_line_ids.filtered(lambda x: x.input_type_id.code == code).mapped("amount"))

    def _cr_month_factor(self):
        self.ensure_one()
        freq = self.contract_id.cr_pay_frequency
        return {"weekly": 52.0/12.0, "biweekly": 2.0, "monthly": 1.0, "hourly": 1.0, "daily": 1.0}.get(freq, 1.0)

    def _cr_monthly_taxable(self, current_taxable):
        self.ensure_one()
        if self.contract_id.cr_pay_frequency == "monthly":
            return current_taxable
        # Acumula otros recibos del mismo mes ya hechos/pagados para evitar duplicar la exención.
        month_start = self.date_to.replace(day=1)
        prior = self.search([
            ("id", "!=", self.id), ("employee_id", "=", self.employee_id.id),
            ("date_to", ">=", month_start), ("date_to", "<=", self.date_to),
            ("state", "in", ["done", "paid"]),
        ])
        prior_taxable = sum(p._cr_taxable_gross_estimate() for p in prior)
        return prior_taxable + current_taxable

    def _cr_taxable_gross_estimate(self):
        self.ensure_one()
        # En recibos finalizados toma la categoría GROSS si está disponible.
        gross = sum(self.line_ids.filtered(lambda l: l.category_id.code == "GROSS").mapped("total"))
        return max(gross, 0.0)

    def _cr_compute_income_tax(self, taxable):
        self.ensure_one()
        Tax = self.env["cr.payroll.tax.bracket"]
        brackets = Tax.search([
            ("active", "=", True), ("date_from", "<=", self.date_to),
            "|", ("date_to", "=", False), ("date_to", ">=", self.date_to),
            "|", ("company_id", "=", self.company_id.id), ("company_id", "=", False),
        ], order="lower_bound")
        monthly_total = self._cr_monthly_taxable(taxable)
        tax_total = 0.0
        for bracket in brackets:
            if monthly_total <= bracket.lower_bound:
                continue
            taxable_part = monthly_total - bracket.lower_bound
            if bracket.upper_bound:
                taxable_part = min(taxable_part, bracket.upper_bound - bracket.lower_bound)
            tax_total += max(taxable_part, 0.0) * bracket.rate / 100.0
        Param = self.env["cr.payroll.legal.parameter"]
        tax_total -= self.employee_id.cr_tax_children * Param.value_at("TAX_CREDIT_CHILD", self.date_to, self.company_id)
        if self.employee_id.cr_tax_spouse:
            tax_total -= Param.value_at("TAX_CREDIT_SPOUSE", self.date_to, self.company_id)
        # Resta lo retenido en recibos anteriores del mismo mes.
        month_start = self.date_to.replace(day=1)
        prior = self.search([
            ("id", "!=", self.id), ("employee_id", "=", self.employee_id.id),
            ("date_to", ">=", month_start), ("date_to", "<=", self.date_to),
            ("state", "in", ["done", "paid"]),
        ])
        prior_tax = abs(sum(prior.mapped("line_ids").filtered(lambda l: l.code == "CR_RENTA").mapped("total")))
        return self._cr_round(max(tax_total - prior_tax, 0.0))

    def _cr_compute_social_component(self, code, taxable):
        self.ensure_one()
        Contribution = self.env["cr.payroll.social.contribution"]
        records = Contribution.search([
            ("code", "=", code), ("active", "=", True),
            ("date_from", "<=", self.date_to),
            "|", ("date_to", "=", False), ("date_to", ">=", self.date_to),
            "|", ("company_id", "=", self.company_id.id), ("company_id", "=", False),
        ], order="company_id desc, date_from desc", limit=1)
        rate = records.rate if records else 0.0
        return self._cr_round(max(taxable, 0.0) * rate / 100.0)

    def _cr_compute_social_employee(self, taxable):
        rate = self.env["cr.payroll.social.contribution"].total_rate_at("employee", self.date_to, self.company_id)
        return self._cr_round(max(taxable, 0.0) * rate / 100.0)

    def _cr_compute_social_employer(self, taxable):
        rate = self.env["cr.payroll.social.contribution"].total_rate_at("employer", self.date_to, self.company_id)
        return self._cr_round(max(taxable, 0.0) * rate / 100.0)

    def _cr_compute_recurring_deductions(self, base):
        self.ensure_one()
        deductions = self.env["cr.payroll.deduction"].search([
            ("employee_id", "=", self.employee_id.id), ("active", "=", True),
            ("date_from", "<=", self.date_to), "|", ("date_to", "=", False), ("date_to", ">=", self.date_from),
        ], order="priority")
        return self._cr_round(sum(d.amount_for_period(base) for d in deductions))

    def _cr_apply_deduction_balances(self):
        for slip in self:
            amount = abs(sum(slip.line_ids.filtered(lambda l: l.code == "CR_RECUR_DED").mapped("total")))
            if not amount:
                continue
            deductions = self.env["cr.payroll.deduction"].search([
                ("employee_id", "=", slip.employee_id.id), ("active", "=", True), ("balance", ">", 0),
            ], order="priority")
            remaining = amount
            for deduction in deductions:
                applied = min(deduction.balance, remaining)
                deduction.balance -= applied
                remaining -= applied
                if deduction.balance <= 0:
                    deduction.active = False
                if remaining <= 0:
                    break


    def _cr_incident_amount(self, incident_type):
        self.ensure_one()
        return sum(self.env["cr.payroll.incident"].search([
            ("employee_id", "=", self.employee_id.id),
            ("date", ">=", self.date_from), ("date", "<=", self.date_to),
            ("incident_type", "=", incident_type), ("state", "=", "approved"),
            ("payslip_id", "in", [False, self.id]),
        ]).mapped("amount"))

    def action_cr_load_incidents(self):
        mapping = {
            "commission": "CR_COMMISSION", "bonus": "CR_BONUS", "incentive": "CR_INCENTIVE",
            "productivity": "CR_PRODUCTIVITY", "availability": "CR_AVAILABILITY",
            "overtime_15": "CR_OT_15", "holiday_work": "CR_OT_20",
            "holiday_overtime": "CR_OT_30", "unpaid_hours": "CR_UNPAID_HOURS",
            "unpaid_days": "CR_UNPAID_DAYS", "tardiness": "CR_TARDINESS",
            "retroactive": "CR_RETROACTIVE", "salary_difference": "CR_SALARY_DIFF",
            "vacation_pay": "CR_VACATION_PAY", "ccss_disability": "CR_CCSS_DISABILITY_PAY",
            "ins_disability": "CR_INS_DISABILITY_PAY", "maternity": "CR_MATERNITY_PAY",
            "paternity": "CR_PATERNITY_PAY", "other_income": "CR_OTHER_INCOME",
            "reimbursement": "CR_REIMBURSEMENT", "other_deduction": "CR_OTHER_DED",
            "aguinaldo_adjustment": "CR_AGUINALDO_ADJ",
        }
        for slip in self:
            incidents = self.env["cr.payroll.incident"].search([
                ("employee_id", "=", slip.employee_id.id), ("date", ">=", slip.date_from),
                ("date", "<=", slip.date_to), ("state", "=", "approved"), ("payslip_id", "=", False),
            ])
            for incident in incidents:
                code = mapping[incident.incident_type]
                input_type = self.env["hr.payslip.input.type"].search([("code", "=", code)], limit=1)
                if input_type:
                    slip.input_line_ids = [(0, 0, {"input_type_id": input_type.id, "amount": incident.amount})]
                    incident.payslip_id = slip.id
        return True


    def _cr_hour_value(self):
        self.ensure_one()
        contract = self.contract_id
        if not contract:
            return 0.0
        if contract.cr_salary_mode == "hourly":
            return contract.wage
        divisor = (contract.cr_days_divisor or 30.0) * (contract.cr_hours_per_day or 8.0)
        return contract.wage / divisor if divisor else 0.0

    def _cr_day_value(self):
        self.ensure_one()
        contract = self.contract_id
        if not contract:
            return 0.0
        if contract.cr_salary_mode == "daily":
            return contract.wage
        divisor = contract.cr_days_divisor or 30.0
        return contract.wage / divisor if divisor else 0.0

    def _cr_input_hours_amount(self, code, multiplier=1.0):
        self.ensure_one()
        # Los inputs de horas guardan cantidad de horas en amount.
        return self._cr_input_amount(code) * self._cr_hour_value() * multiplier

    def _cr_unpaid_time_amount(self):
        self.ensure_one()
        hours = self._cr_input_amount("CR_UNPAID_HOURS") + self._cr_input_amount("CR_TARDINESS")
        days = self._cr_input_amount("CR_UNPAID_DAYS")
        return self._cr_round(hours * self._cr_hour_value() + days * self._cr_day_value())

    def _cr_variable_taxable_inputs(self):
        self.ensure_one()
        codes = ["CR_COMMISSION", "CR_BONUS", "CR_INCENTIVE", "CR_PRODUCTIVITY",
                 "CR_AVAILABILITY", "CR_RETROACTIVE", "CR_SALARY_DIFF",
                 "CR_OTHER_INCOME", "CR_VIATIC_TAXABLE"]
        return sum(self._cr_input_amount(code) for code in codes)

    def _cr_compute_aguinaldo(self):
        self.ensure_one()
        start = fields.Date.to_date("%s-12-01" % (self.date_to.year - 1))
        end = fields.Date.to_date("%s-11-30" % self.date_to.year)
        slips = self.search([
            ("employee_id", "=", self.employee_id.id), ("state", "in", ["done", "paid"]),
            ("date_to", ">=", start), ("date_to", "<=", end),
        ])
        # Todo ingreso marcado en categorías ordinarias/variables; excluye reembolsos y el propio aguinaldo.
        eligible_codes = {"BASIC", "REGULAR", "VARIABLE", "OVERTIME", "ALLOWANCE"}
        total = sum(line.total for slip in slips for line in slip.line_ids if line.category_id.code in eligible_codes and line.code != "CR_AGUINALDO")
        total += self._cr_input_amount("CR_AGUINALDO_ADJ")
        return self._cr_round(max(total / 12.0, 0.0))
