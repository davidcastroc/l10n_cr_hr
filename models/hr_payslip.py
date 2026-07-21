# -*- coding: utf-8 -*-
from calendar import monthrange
from collections import defaultdict
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    cr_validation_message = fields.Text(compute="_compute_cr_validation_message")
    cr_incident_ids = fields.One2many("cr.payroll.incident", "payslip_id", string="Incidencias CR")
    cr_deduction_movement_ids = fields.One2many("cr.payroll.deduction.movement", "payslip_id", string="Movimientos de deducciones")

    def _cr_round(self, amount):
        self.ensure_one()
        return round(amount) if self.company_id.cr_payroll_rounding == "colon" else round(amount, 2)

    def _cr_input_amount(self, code):
        self.ensure_one()
        return sum(self.input_line_ids.filtered(lambda line: line.input_type_id.code == code).mapped("amount"))

    def _cr_worked_days(self, code):
        self.ensure_one()
        lines = self.worked_days_line_ids.filtered(lambda line: line.code == code)
        return sum(lines.mapped("number_of_days")), sum(lines.mapped("number_of_hours"))

    def _cr_regular_hours(self):
        self.ensure_one()
        leave_codes = {"CR_UNPAID", "CR_SICK_CCSS", "CR_SICK_INS", "CR_MATERNITY", "CR_PATERNITY", "CR_BREASTFEEDING"}
        return sum(self.worked_days_line_ids.filtered(lambda line: line.code not in leave_codes).mapped("number_of_hours"))

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

    def _cr_basic_amount(self, frequency):
        self.ensure_one()
        wage = self.contract_id.wage or 0.0
        if frequency == "monthly":
            return wage
        if frequency == "biweekly":
            return wage / 2.0
        if frequency == "weekly":
            return wage * 12.0 / 52.0
        if frequency == "hourly":
            return self._cr_regular_hours() * wage
        return wage

    def _cr_input_hours_amount(self, code, multiplier=1.0):
        self.ensure_one()
        return self._cr_input_amount(code) * self._cr_hour_value() * multiplier

    def _cr_holiday_worked_amount(self):
        self.ensure_one()
        multiplier = 1.0 if self.contract_id.cr_pay_frequency in ("monthly", "biweekly") else 2.0
        return self._cr_input_hours_amount("CR_OT_20", multiplier)

    def _cr_unpaid_time_amount(self):
        self.ensure_one()
        _days, leave_hours = self._cr_worked_days("CR_UNPAID")
        manual_hours = self._cr_input_amount("CR_UNPAID_HOURS") + self._cr_input_amount("CR_TARDINESS")
        manual_days = self._cr_input_amount("CR_UNPAID_DAYS")
        return self._cr_round((leave_hours + manual_hours) * self._cr_hour_value() + manual_days * self._cr_day_value())

    def _cr_variable_taxable_inputs(self):
        self.ensure_one()
        codes = ["CR_COMMISSION", "CR_BONUS", "CR_INCENTIVE", "CR_PRODUCTIVITY", "CR_AVAILABILITY", "CR_RETROACTIVE", "CR_SALARY_DIFF", "CR_OTHER_INCOME", "CR_VIATIC_TAXABLE"]
        return sum(self._cr_input_amount(code) for code in codes)

    def _cr_prior_month_payslips(self):
        self.ensure_one()
        month_start = self.date_to.replace(day=1)
        month_end = self.date_to.replace(day=monthrange(self.date_to.year, self.date_to.month)[1])
        return self.search([
            ("id", "!=", self.id),
            ("employee_id", "=", self.employee_id.id),
            ("company_id", "=", self.company_id.id),
            ("date_to", ">=", month_start),
            ("date_to", "<=", month_end),
            ("state", "in", ["done", "paid"]),
        ])

    def _cr_taxable_gross_estimate(self):
        self.ensure_one()
        return max(sum(self.line_ids.filtered(lambda line: line.code == "GROSS").mapped("total")), 0.0)

    def _cr_monthly_taxable(self, current_taxable):
        self.ensure_one()
        return sum(slip._cr_taxable_gross_estimate() for slip in self._cr_prior_month_payslips()) + max(current_taxable, 0.0)

    def _cr_compute_income_tax(self, taxable):
        self.ensure_one()
        brackets = self.env["cr.payroll.tax.bracket"].search([
            ("active", "=", True),
            ("date_from", "<=", self.date_to),
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
        params = self.env["cr.payroll.legal.parameter"]
        tax_total -= self.employee_id.cr_tax_children * params.value_at("TAX_CREDIT_CHILD", self.date_to, self.company_id)
        if self.employee_id.cr_tax_spouse:
            tax_total -= params.value_at("TAX_CREDIT_SPOUSE", self.date_to, self.company_id)
        prior_tax = abs(sum(self._cr_prior_month_payslips().mapped("line_ids").filtered(lambda line: line.code == "CR_RENTA").mapped("total")))
        return self._cr_round(max(tax_total - prior_tax, 0.0))

    def _cr_social_minimum_base(self, code):
        self.ensure_one()
        if self.employee_id.cr_bmc_exempt:
            return 0.0
        params = self.env["cr.payroll.legal.parameter"]
        if not params.value_at("BMC_ENABLED", self.date_to, self.company_id, default=1.0):
            return 0.0
        if code.startswith("SEM_"):
            return params.value_at("BMC_SEM", self.date_to, self.company_id)
        if code.startswith("IVM_"):
            return params.value_at("BMC_IVM", self.date_to, self.company_id)
        return 0.0

    def _cr_compute_social_component(self, code, taxable):
        self.ensure_one()
        contribution = self.env["cr.payroll.social.contribution"].rate_at(code, self.date_to, self.company_id)
        if not contribution:
            return 0.0
        prior_slips = self._cr_prior_month_payslips()
        prior_gross = sum(slip._cr_taxable_gross_estimate() for slip in prior_slips)
        prior_component = abs(sum(prior_slips.mapped("line_ids").filtered(lambda line: line.code == "CR_%s" % code).mapped("total")))
        current_gross = max(taxable, 0.0)
        month_days = monthrange(self.date_to.year, self.date_to.month)[1]
        elapsed_days = self.date_to.day
        minimum_to_date = self._cr_social_minimum_base(code) * elapsed_days / month_days
        cumulative_base = max(prior_gross + current_gross, minimum_to_date)
        target = cumulative_base * contribution.rate / 100.0
        return self._cr_round(max(target - prior_component, 0.0))

    def _cr_disability_days(self, code):
        mapping = {"CCSS": "CR_SICK_CCSS", "INS": "CR_SICK_INS", "MATERNITY": "CR_MATERNITY"}
        days, hours = self._cr_worked_days(mapping[code])
        if days:
            return days
        return hours / (self.contract_id.cr_hours_per_day or 8.0)

    def _cr_disability_amounts(self):
        self.ensure_one()
        result = {"deduction": 0.0, "employer_taxable": 0.0, "employer_nontaxable": 0.0,
                   "subsidy": 0.0, "aguinaldo_base": 0.0}
        Rule = self.env["cr.payroll.disability.rule"]
        for code in ("CCSS", "INS", "MATERNITY"):
            days = self._cr_disability_days(code)
            if not days:
                continue
            rules = Rule.search([
                ("code", "=", code), ("active", "=", True),
                ("date_from", "<=", self.date_to),
                "|", ("date_to", "=", False), ("date_to", ">=", self.date_from),
                "|", ("company_id", "=", self.company_id.id), ("company_id", "=", False),
            ], order="day_from")
            if not rules:
                raise UserError("Existe una ausencia %s sin regla activa de incapacidad." % code)
            daily = self._cr_day_value()
            for rule in rules:
                upper = rule.day_to or days
                covered = max(min(days, upper) - rule.day_from + 1.0, 0.0)
                if not covered:
                    continue
                base = covered * daily
                result["deduction"] += base * rule.deduction_rate / 100.0
                employer = base * rule.employer_rate / 100.0
                if rule.employer_payment_taxable:
                    result["employer_taxable"] += employer
                else:
                    result["employer_nontaxable"] += employer
                if rule.affects_aguinaldo:
                    result["aguinaldo_base"] += employer
                if rule.subsidy_paid_in_payroll:
                    result["subsidy"] += base * rule.subsidy_rate / 100.0
        return {key: self._cr_round(value) for key, value in result.items()}

    def _cr_disability_deduction_amount(self):
        return self._cr_disability_amounts()["deduction"]

    def _cr_disability_employer_taxable_amount(self):
        return self._cr_disability_amounts()["employer_taxable"]

    def _cr_disability_employer_nontaxable_amount(self):
        return self._cr_disability_amounts()["employer_nontaxable"]

    def _cr_disability_subsidy_amount(self):
        return self._cr_disability_amounts()["subsidy"]

    def _cr_disability_aguinaldo_base_amount(self):
        return self._cr_disability_amounts()["aguinaldo_base"]

    def _cr_active_deductions(self):
        self.ensure_one()
        return self.env["cr.payroll.deduction"].search([
            ("employee_id", "=", self.employee_id.id),
            ("active", "=", True),
            ("date_from", "<=", self.date_to),
            "|", ("date_to", "=", False), ("date_to", ">=", self.date_from),
        ], order="priority, id")

    def _cr_compute_recurring_deductions(self, base):
        self.ensure_one()
        return self._cr_round(sum(deduction.amount_for_period(base) for deduction in self._cr_active_deductions()))

    def _cr_apply_deduction_balances(self):
        Movement = self.env["cr.payroll.deduction.movement"]
        for slip in self:
            if slip.cr_deduction_movement_ids.filtered(lambda movement: movement.state == "applied"):
                continue
            remaining = abs(sum(slip.line_ids.filtered(lambda line: line.code == "CR_RECUR_DED").mapped("total")))
            for deduction in slip._cr_active_deductions():
                if remaining <= 0:
                    break
                amount = min(deduction.amount_for_period(slip._cr_taxable_gross_estimate()), remaining)
                if not amount:
                    continue
                Movement.create({"deduction_id": deduction.id, "payslip_id": slip.id, "amount": amount})
                if deduction.original_amount or deduction.balance:
                    deduction.balance = max(deduction.balance - amount, 0.0)
                    if deduction.balance == 0.0:
                        deduction.active = False
                remaining -= amount

    def _cr_reverse_deduction_balances(self):
        for slip in self:
            for movement in slip.cr_deduction_movement_ids.filtered(lambda item: item.state == "applied"):
                deduction = movement.deduction_id.with_context(active_test=False)
                if deduction.original_amount or deduction.balance:
                    deduction.balance += movement.amount
                    deduction.active = True
                movement.state = "reversed"

    def _cr_compute_aguinaldo(self):
        self.ensure_one()
        if self.date_to.month == 12:
            start = date(self.date_to.year - 1, 12, 1)
            end = date(self.date_to.year, 11, 30)
        else:
            start_year = self.date_to.year - 1 if self.date_to.month < 12 else self.date_to.year
            start = date(start_year, 12, 1)
            end = self.date_to
        slips = self.search([
            ("employee_id", "=", self.employee_id.id),
            ("state", "in", ["done", "paid"]),
            ("date_to", ">=", start),
            ("date_to", "<=", end),
        ])
        excluded = {"CR_AGUINALDO", "CR_REIMBURSEMENT", "CR_DISABILITY_SUBSIDY",
                    "CR_DISABILITY_EMP_TAX", "CR_DISABILITY_EMP_NONTAX"}
        eligible_categories = {"BASIC", "VARIABLE", "OVERTIME", "ALLOWANCE", "AGUINALDO_BASE"}
        total = sum(line.total for slip in slips for line in slip.line_ids if line.category_id.code in eligible_categories and line.code not in excluded)
        total += self._cr_input_amount("CR_AGUINALDO_ADJ")
        return self._cr_round(max(total / 12.0, 0.0))

    def action_cr_load_incidents(self):
        mapping = {
            "commission": "CR_COMMISSION", "bonus": "CR_BONUS", "incentive": "CR_INCENTIVE",
            "productivity": "CR_PRODUCTIVITY", "availability": "CR_AVAILABILITY",
            "overtime_15": "CR_OT_15", "holiday_work": "CR_OT_20", "holiday_overtime": "CR_OT_30",
            "unpaid_hours": "CR_UNPAID_HOURS", "unpaid_days": "CR_UNPAID_DAYS", "tardiness": "CR_TARDINESS",
            "retroactive": "CR_RETROACTIVE", "salary_difference": "CR_SALARY_DIFF",
            "vacation_pay": "CR_VACATION_PAY", "other_income": "CR_OTHER_INCOME",
            "reimbursement": "CR_REIMBURSEMENT", "other_deduction": "CR_OTHER_DED",
            "aguinaldo_adjustment": "CR_AGUINALDO_ADJ",
        }
        Input = self.env["hr.payslip.input.type"]
        Incident = self.env["cr.payroll.incident"]
        for slip in self:
            incidents = Incident.search([
                ("employee_id", "=", slip.employee_id.id),
                ("date", ">=", slip.date_from), ("date", "<=", slip.date_to),
                ("state", "=", "approved"), ("payslip_id", "=", False),
            ])
            totals = defaultdict(float)
            grouped = defaultdict(lambda: Incident.browse())
            for incident in incidents:
                code = mapping.get(incident.incident_type)
                if code:
                    totals[code] += incident.amount
                    grouped[code] |= incident
            for code, amount in totals.items():
                input_type = Input.search([("code", "=", code)], limit=1)
                if not input_type:
                    continue
                line = slip.input_line_ids.filtered(lambda item: item.input_type_id == input_type)[:1]
                if line:
                    line.amount += amount
                else:
                    slip.write({"input_line_ids": [(0, 0, {"input_type_id": input_type.id, "amount": amount})]})
                grouped[code].write({"payslip_id": slip.id})
        return True

    def _cr_work_entry_issues(self):
        self.ensure_one()
        issues = []
        if "hr.work.entry" not in self.env:
            return issues
        entries = self.env["hr.work.entry"].search([
            ("employee_id", "=", self.employee_id.id),
            ("date_start", "<=", fields.Datetime.to_datetime(self.date_to)),
            ("date_stop", ">=", fields.Datetime.to_datetime(self.date_from)),
        ])
        invalid = entries.filtered(lambda entry: entry.state != "validated")
        if invalid:
            issues.append("Hay %s entradas de trabajo sin validar o en conflicto." % len(invalid))
        return issues

    @api.depends("employee_id", "contract_id", "date_from", "date_to", "state")
    def _compute_cr_validation_message(self):
        for slip in self:
            issues = []
            if not slip.contract_id:
                issues.append("Empleado sin contrato en el recibo.")
            else:
                if slip.contract_id.wage <= 0:
                    issues.append("El salario contractual debe ser mayor que cero.")
                if not slip.contract_id.resource_calendar_id:
                    issues.append("El contrato no tiene horario laboral.")
                if slip.date_from and slip.date_to and not slip.contract_id.cr_period_is_valid(slip.date_from, slip.date_to):
                    issues.append("El período no coincide con la frecuencia de pago del contrato.")
                if slip.contract_id.date_start and slip.date_from and slip.date_from < slip.contract_id.date_start:
                    issues.append("El recibo inicia antes de la fecha de inicio del contrato.")
                if slip.contract_id.date_end and slip.date_to and slip.date_to > slip.contract_id.date_end:
                    issues.append("El recibo termina después de la fecha final del contrato.")
            if not slip.employee_id.identification_id:
                issues.append("Falta identificación del empleado.")
            if not slip.employee_id.bank_account_id:
                issues.append("Falta cuenta bancaria del empleado.")
            if slip.date_from and slip.date_to and slip.date_from > slip.date_to:
                issues.append("El período del recibo es inválido.")
            if slip.employee_id and slip.date_from and slip.date_to and self.search_count([
                ("id", "!=", slip.id), ("employee_id", "=", slip.employee_id.id),
                ("date_from", "=", slip.date_from), ("date_to", "=", slip.date_to),
                ("state", "in", ["done", "paid"]),
            ]):
                issues.append("Ya existe otro recibo finalizado para el mismo empleado y período.")
            if slip.id:
                issues.extend(slip._cr_work_entry_issues())
            slip.cr_validation_message = "\n".join(issues)

    def action_payslip_done(self):
        for slip in self:
            if slip.cr_validation_message:
                raise UserError("No se puede cerrar la nómina:\n%s" % slip.cr_validation_message)
        result = super().action_payslip_done()
        self._cr_apply_deduction_balances()
        self.mapped("cr_incident_ids").filtered(lambda incident: incident.state == "approved").write({"state": "applied"})
        return result

    def action_payslip_draft(self):
        self._cr_reverse_deduction_balances()
        self.mapped("cr_incident_ids").filtered(lambda incident: incident.state == "applied").write({"state": "approved", "payslip_id": False})
        return super().action_payslip_draft()
