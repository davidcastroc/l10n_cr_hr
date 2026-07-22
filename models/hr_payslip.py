# -*- coding: utf-8 -*-
import calendar
from collections import defaultdict
from odoo import _, api, fields, models
from odoo.exceptions import UserError

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    cr_validation_message = fields.Text(compute="_compute_cr_validation_message")
    cr_incident_ids = fields.One2many("cr.payroll.incident", "payslip_id", string="Incidencias CR")

    def _compute_cr_validation_message(self):
        WorkEntry = self.env["hr.work.entry"].sudo()
        for slip in self:
            issues = []
            contract = slip.contract_id
            if not contract:
                issues.append("Empleado sin contrato en el recibo.")
            else:
                if contract.wage <= 0:
                    issues.append("El salario contractual debe ser mayor que cero.")
                if not contract.resource_calendar_id:
                    issues.append("El contrato no tiene horario laboral.")
                if slip.date_from and contract.date_start and slip.date_from < contract.date_start:
                    issues.append("El recibo inicia antes de la vigencia del contrato.")
                if slip.date_to and contract.date_end and slip.date_to > contract.date_end:
                    issues.append("El recibo finaliza después de la vigencia del contrato.")
                if slip.date_from and slip.date_to:
                    days = (slip.date_to - slip.date_from).days + 1
                    expected = {
                        "weekly": (6, 8),
                        "biweekly": (14, 16),
                        "monthly": (28, 31),
                    }.get(contract.cr_pay_frequency)
                    if expected and not expected[0] <= days <= expected[1]:
                        issues.append(
                            "El período de %s días no coincide con la frecuencia %s."
                            % (days, dict(contract._fields["cr_pay_frequency"].selection).get(contract.cr_pay_frequency))
                        )
            if not slip.employee_id.identification_id:
                issues.append("Falta identificación del empleado.")
            if not slip.employee_id.bank_account_id:
                issues.append("Falta cuenta bancaria del empleado.")
            if slip.date_from and slip.date_to and slip.date_from > slip.date_to:
                issues.append("El período del recibo es inválido.")

            if contract and slip.date_from and slip.date_to:
                missing = slip._cr_missing_disability_configuration()
                if missing:
                    issues.append("Falta configurar una regla activa para: %s." % ", ".join(missing))
                attendance_hours = slip._cr_worked_hours(["WORK100", "WORK", "ATTENDANCE"])
                period_days = (slip.date_to - slip.date_from).days + 1
                if attendance_hours > period_days * 24.0:
                    issues.append(
                        "Las entradas de trabajo muestran %.2f horas en %s días; regenere las entradas del período."
                        % (attendance_hours, period_days)
                    )
                domain = [
                    ("employee_id", "=", slip.employee_id.id),
                    ("date_start", "<=", fields.Datetime.to_string(fields.Datetime.to_datetime(slip.date_to).replace(hour=23, minute=59, second=59))),
                    ("date_stop", ">=", fields.Datetime.to_datetime(slip.date_from)),
                ]
                work_entries = WorkEntry.search(domain)
                if "state" in WorkEntry._fields:
                    bad_states = work_entries.filtered(lambda entry: entry.state in ("draft", "conflict"))
                    if bad_states:
                        issues.append("Existen entradas de trabajo en borrador o conflicto dentro del período.")

            duplicate = self.search_count([
                ("id", "!=", slip.id),
                ("employee_id", "=", slip.employee_id.id),
                ("date_from", "=", slip.date_from),
                ("date_to", "=", slip.date_to),
                ("state", "not in", ["cancel"]),
            ])
            if slip.employee_id and duplicate:
                issues.append("Ya existe otro recibo para el mismo empleado y período.")
            slip.cr_validation_message = "\n".join(issues)

    def action_payslip_done(self):
        for slip in self:
            if slip.cr_validation_message:
                raise UserError("No se puede cerrar la nómina:\n%s" % slip.cr_validation_message)
        result = super().action_payslip_done()
        self._cr_apply_deduction_balances()
        self.mapped("cr_incident_ids").filtered(lambda x: x.state == "approved").write({"state": "applied"})
        return result


    def action_payslip_draft(self):
        self._cr_reverse_deduction_balances()
        return super().action_payslip_draft()

    def action_payslip_cancel(self):
        self._cr_reverse_deduction_balances()
        return super().action_payslip_cancel()

    def _cr_round(self, amount):
        self.ensure_one()
        return round(amount) if self.company_id.cr_payroll_rounding == "colon" else round(amount, 2)

    def _cr_input_amount(self, code):
        self.ensure_one()
        return sum(self.input_line_ids.filtered(lambda x: x.input_type_id.code == code).mapped("amount"))

    def _cr_worked_day_lines(self, codes):
        self.ensure_one()
        if isinstance(codes, str):
            codes = [codes]
        return self.worked_days_line_ids.filtered(
            lambda line: line.work_entry_type_id.code in codes
        )

    def _cr_worked_days(self, codes):
        self.ensure_one()
        return sum(self._cr_worked_day_lines(codes).mapped("number_of_days"))

    def _cr_worked_hours(self, codes):
        self.ensure_one()
        return sum(self._cr_worked_day_lines(codes).mapped("number_of_hours"))

    def _cr_has_recurring_deductions(self):
        self.ensure_one()
        return bool(self.env["cr.payroll.deduction"].search_count([
            ("employee_id", "=", self.employee_id.id),
            ("active", "=", True),
            ("date_from", "<=", self.date_to),
            "|", ("date_to", "=", False), ("date_to", ">=", self.date_from),
        ]))

    def _cr_disability_profiles(self):
        """Retorna los perfiles de ausencias detectadas en las entradas de trabajo."""
        self.ensure_one()
        mapping = {
            "CR_SICK_CCSS": "CCSS",
            "CR_SICK_INS": "INS",
            "CR_MATERNITY": "MATERNITY",
            "CR_PATERNITY": "PATERNITY",
        }
        profiles = []
        Rule = self.env["cr.payroll.disability.rule"].sudo()
        for work_code, rule_code in mapping.items():
            days = self._cr_worked_days(work_code)
            hours = self._cr_worked_hours(work_code)
            if not days and not hours:
                continue
            if not days and hours:
                days = hours / (self.contract_id.cr_hours_per_day or 8.0)
            rules = Rule.search([
                ("code", "=", rule_code),
                ("active", "=", True),
                ("date_from", "<=", self.date_to),
                "|", ("date_to", "=", False), ("date_to", ">=", self.date_from),
                "|", ("company_id", "=", self.company_id.id), ("company_id", "=", False),
            ], order="company_id desc, day_from")
            profiles.append((work_code, rule_code, days, rules))
        return profiles

    def _cr_missing_disability_configuration(self):
        self.ensure_one()
        missing = []
        for _work_code, rule_code, _days, rules in self._cr_disability_profiles():
            if not rules:
                missing.append(rule_code)
        return sorted(set(missing))

    def _cr_disability_amounts(self):
        """Calcula rebajo, pago patronal y subsidio adelantado sin duplicar salario.

        El salario fijo se calcula completo para el período. Por eso primero se rebaja
        la porción ordinaria correspondiente a la ausencia y luego se agregan las
        porciones que efectivamente paga la empresa.
        """
        self.ensure_one()
        deduction = employer_taxable = employer_nontaxable = subsidy_advance = subsidy_info = 0.0
        day_value = self._cr_day_value()
        for _work_code, _rule_code, days, rules in self._cr_disability_profiles():
            for rule in rules:
                upper = rule.day_to or days
                covered = max(min(days, upper) - rule.day_from + 1.0, 0.0)
                if not covered:
                    continue
                base = covered * day_value
                deduction += base * rule.deduction_rate / 100.0
                employer = base * rule.employer_rate / 100.0
                if rule.employer_payment_taxable:
                    employer_taxable += employer
                else:
                    employer_nontaxable += employer
                subsidy = base * rule.subsidy_rate / 100.0
                subsidy_info += subsidy
                if rule.subsidy_paid_in_payroll:
                    subsidy_advance += subsidy
        return {
            "deduction": self._cr_round(deduction),
            "employer_taxable": self._cr_round(employer_taxable),
            "employer_nontaxable": self._cr_round(employer_nontaxable),
            "subsidy_advance": self._cr_round(subsidy_advance),
            "subsidy_info": self._cr_round(subsidy_info),
        }

    def _cr_disability_deduction_amount(self):
        self.ensure_one()
        return self._cr_disability_amounts()["deduction"]

    def _cr_disability_employer_taxable_amount(self):
        self.ensure_one()
        return self._cr_disability_amounts()["employer_taxable"]

    def _cr_disability_employer_nontaxable_amount(self):
        self.ensure_one()
        manual = (
            self._cr_input_amount("CR_CCSS_DISABILITY_PAY")
            + self._cr_input_amount("CR_INS_DISABILITY_PAY")
            + self._cr_input_amount("CR_MATERNITY_PAY")
            + self._cr_input_amount("CR_PATERNITY_PAY")
        )
        return self._cr_round(self._cr_disability_amounts()["employer_nontaxable"] + manual)

    def _cr_disability_subsidy_advance_amount(self):
        self.ensure_one()
        return self._cr_disability_amounts()["subsidy_advance"]

    def _cr_disability_subsidy_information(self):
        self.ensure_one()
        return self._cr_disability_amounts()["subsidy_info"]

    def _cr_disability_total_amount(self):
        self.ensure_one()
        amounts = self._cr_disability_amounts()
        return self._cr_round(
            amounts["employer_taxable"]
            + amounts["employer_nontaxable"]
            + amounts["subsidy_advance"]
        )

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
        """Calcula una contribución social acumulada dentro del mes.

        La base mínima de SEM/IVM se aplica proporcionalmente al avance del
        período mensual. Esto evita cobrar la base mínima mensual completa en
        la primera quincena y volver a recalcularla en la segunda.

        Ejemplo quincenal:
        - Primera quincena: se considera hasta el 50 % de la base mínima.
        - Segunda quincena: se completa hasta el 100 % de la base mínima.
        - Si el salario gravable acumulado supera la base mínima proporcional,
          se utiliza el salario gravable real.
        """
        self.ensure_one()

        if not self.date_to:
            return 0.0

        Contribution = self.env["cr.payroll.social.contribution"]
        record = Contribution.search([
            ("code", "=", code),
            ("active", "=", True),
            ("date_from", "<=", self.date_to),
            "|",
            ("date_to", "=", False),
            ("date_to", ">=", self.date_to),
            "|",
            ("company_id", "=", self.company_id.id),
            ("company_id", "=", False),
        ], order="company_id desc, date_from desc", limit=1)

        if not record or not record.rate:
            return 0.0

        month_start = self.date_to.replace(day=1)
        prior_slips = self.search([
            ("id", "!=", self.id),
            ("employee_id", "=", self.employee_id.id),
            ("company_id", "=", self.company_id.id),
            ("date_to", ">=", month_start),
            ("date_to", "<", self.date_to),
            ("state", "in", ["done", "paid"]),
        ])

        prior_taxable = sum(
            slip._cr_taxable_gross_estimate()
            for slip in prior_slips
        )
        accumulated_taxable = max(
            prior_taxable + max(taxable or 0.0, 0.0),
            0.0,
        )

        Param = self.env["cr.payroll.legal.parameter"]
        minimum_code = {
            "SEM_EMP": "SEM_MIN_BASE",
            "SEM_PAT": "SEM_MIN_BASE",
            "IVM_EMP": "IVM_MIN_BASE",
            "IVM_PAT": "IVM_MIN_BASE",
        }.get(code)

        contribution_base = accumulated_taxable

        if minimum_code and accumulated_taxable > 0:
            monthly_minimum = max(
                Param.value_at(
                    minimum_code,
                    self.date_to,
                    self.company_id,
                ) or 0.0,
                0.0,
            )

            # Se prorratea la base mínima según el avance real del mes.
            # Al día 15 de un mes de 30 días aplica el 50 %; al cierre aplica 100 %.
            days_in_month = calendar.monthrange(
                self.date_to.year,
                self.date_to.month,
            )[1]
            elapsed_ratio = min(
                max(self.date_to.day / float(days_in_month), 0.0),
                1.0,
            )
            prorated_minimum = monthly_minimum * elapsed_ratio
            contribution_base = max(
                accumulated_taxable,
                prorated_minimum,
            )

        total_due = contribution_base * record.rate / 100.0

        salary_code = {
            "SEM_EMP": "CR_SEM_EMP",
            "IVM_EMP": "CR_IVM_EMP",
            "BP_EMP": "CR_BP_EMP",
            "SEM_PAT": "CR_SEM_PAT",
            "IVM_PAT": "CR_IVM_PAT",
            "BP_PAT": "CR_BP_PAT",
            "FODESAF_PAT": "CR_FODESAF_PAT",
            "IMAS_PAT": "CR_IMAS_PAT",
            "INA_PAT": "CR_INA_PAT",
            "FCL_PAT": "CR_FCL_PAT",
            "ROP_PAT": "CR_ROP_PAT",
        }.get(code)

        prior_paid = 0.0
        if salary_code:
            prior_paid = abs(sum(
                prior_slips.mapped("line_ids")
                .filtered(lambda line: line.code == salary_code)
                .mapped("total")
            ))

        current_due = max(total_due - prior_paid, 0.0)
        return self._cr_round(current_due)

    def _cr_compute_social_employee(self, taxable):
        rate = self.env["cr.payroll.social.contribution"].total_rate_at("employee", self.date_to, self.company_id)
        return self._cr_round(max(taxable, 0.0) * rate / 100.0)

    def _cr_compute_social_employer(self, taxable):
        rate = self.env["cr.payroll.social.contribution"].total_rate_at("employer", self.date_to, self.company_id)
        return self._cr_round(max(taxable, 0.0) * rate / 100.0)

    def _cr_compute_recurring_deductions(self, base):
        self.ensure_one()
        deductions = self.env["cr.payroll.deduction"].search([
            ("employee_id", "=", self.employee_id.id),
            ("active", "=", True),
            ("date_from", "<=", self.date_to),
            "|", ("date_to", "=", False), ("date_to", ">=", self.date_from),
        ], order="priority, id")
        return self._cr_round(sum(
            deduction.amount_for_period(base, payslip=self)
            for deduction in deductions
        ))

    def _cr_apply_deduction_balances(self):
        Movement = self.env["cr.payroll.deduction.movement"].sudo()
        for slip in self:
            if Movement.search_count([("payslip_id", "=", slip.id), ("state", "=", "applied")]):
                continue
            amount = abs(sum(
                slip.line_ids.filtered(lambda line: line.code == "CR_RECUR_DED").mapped("total")
            ))
            if not amount:
                continue
            deductions = self.env["cr.payroll.deduction"].search([
                ("employee_id", "=", slip.employee_id.id),
                ("active", "=", True),
                ("date_from", "<=", slip.date_to),
                "|", ("date_to", "=", False), ("date_to", ">=", slip.date_from),
            ], order="priority, id")
            remaining = amount
            for deduction in deductions:
                if remaining <= 0:
                    break
                expected = deduction.amount_for_period(
                    max(slip._cr_taxable_gross_estimate(), 0.0), payslip=slip
                )
                if not expected:
                    continue
                available = deduction.balance if deduction.balance else expected
                applied = min(expected, available, remaining)
                if not applied:
                    continue
                before = deduction.balance
                after = max(before - applied, 0.0) if before else 0.0
                Movement.create({
                    "deduction_id": deduction.id,
                    "payslip_id": slip.id,
                    "date": slip.date_to,
                    "amount": applied,
                    "balance_before": before,
                    "balance_after": after,
                    "state": "applied",
                })
                if before:
                    deduction.balance = after
                    if after <= 0:
                        deduction.active = False
                remaining -= applied

    def _cr_reverse_deduction_balances(self):
        Movement = self.env["cr.payroll.deduction.movement"].sudo()
        for slip in self:
            movements = Movement.search([
                ("payslip_id", "=", slip.id),
                ("state", "=", "applied"),
            ])
            for movement in movements:
                deduction = movement.deduction_id
                if movement.balance_before:
                    deduction.balance = movement.balance_before
                    deduction.active = True
                movement.state = "reversed"

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


    def _cr_holiday_work_amount(self):
        self.ensure_one()
        hours = self._cr_input_amount("CR_OT_20")
        multiplier = 1.0 if self.contract_id.cr_pay_frequency in ("monthly", "biweekly") else 2.0
        return self._cr_round(hours * self._cr_hour_value() * multiplier)

    def _cr_unpaid_time_amount(self):
        self.ensure_one()
        manual_hours = self._cr_input_amount("CR_UNPAID_HOURS") + self._cr_input_amount("CR_TARDINESS")
        manual_days = self._cr_input_amount("CR_UNPAID_DAYS")
        work_hours = self._cr_worked_hours("CR_UNPAID")
        work_days = self._cr_worked_days("CR_UNPAID")
        work_amount = (
            work_hours * self._cr_hour_value()
            if work_hours
            else work_days * self._cr_day_value()
        )
        return self._cr_round(
            manual_hours * self._cr_hour_value()
            + manual_days * self._cr_day_value()
            + work_amount
        )

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
        opening = self.employee_id.cr_aguinaldo_opening_earnings or 0.0
        opening_date = self.employee_id.cr_aguinaldo_opening_date
        if opening_date and not (start <= opening_date <= end):
            opening = 0.0
        total += opening
        total += self._cr_input_amount("CR_AGUINALDO_ADJ")
        return self._cr_round(max(total / 12.0, 0.0))
