# -*- coding: utf-8 -*-
import calendar
from collections import defaultdict
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import date_utils

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    cr_validation_message = fields.Text(compute="_compute_cr_validation_message")
    cr_incident_ids = fields.One2many("cr.payroll.incident", "payslip_id", string="Incidencias CR")

    cr_basic_total = fields.Monetary(string="Salario básico", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_gross_total = fields.Monetary(string="Salario bruto", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_employee_ccss_total = fields.Monetary(string="CCSS trabajador", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_income_tax_total = fields.Monetary(string="Renta", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_recurring_deduction_total = fields.Monetary(string="Deducciones recurrentes", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_total_deductions = fields.Monetary(string="Deducciones totales", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_net_total = fields.Monetary(string="Salario neto", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_employer_social_total = fields.Monetary(string="Cargas patronales", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_aguinaldo_period_total = fields.Monetary(string="Provisión aguinaldo", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_vacation_provision_total = fields.Monetary(string="Provisión vacaciones", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_employer_cost_total = fields.Monetary(string="Costo patronal", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")
    cr_aguinaldo_accumulated = fields.Monetary(string="Aguinaldo acumulado", compute="_compute_cr_dashboard_amounts", currency_field="currency_id")

    cr_termination_id = fields.Many2one(
        "cr.payroll.termination",
        string="Liquidación laboral CR",
        copy=False,
        ondelete="restrict",
    )

    def _cr_is_special_process(self):
        self.ensure_one()
        usage = getattr(self.struct_id, "cr_structure_usage", False)
        return usage in ("aguinaldo", "extraordinary", "termination", "settlement")

    def _cr_is_settlement_structure(self):
        """Indica si el recibo utiliza la estructura especial de liquidación CR."""
        self.ensure_one()

        settlement_structure = self.env.ref(
            "l10n_cr_hr.structure_settlement",
            raise_if_not_found=False,
        )

        return bool(
            settlement_structure
            and self.struct_id == settlement_structure
        )

    @api.depends(
        "date_from",
        "date_to",
        "struct_id",
        "contract_id.date_start",
        "contract_id.date_end",
    )
    def _compute_warning_message(self):
        """
        Conserva los warnings estándar de Odoo Enterprise, excepto el warning
        de duración para la estructura especial CR - Liquidación laboral.

        Una liquidación se emite con fecha inicial = fecha final = fecha de
        terminación, por lo que no debe compararse contra la periodicidad
        ordinaria del contrato.
        """
        for slip in self:
            slip.warning_message = False

            if not slip.date_from or not slip.date_to:
                continue

            warnings = []

            if slip._is_payslip_not_in_contract():
                warnings.append(
                    _("No running contract over payslip period")
                )

            if slip.date_to > date_utils.end_of(
                fields.Date.today(),
                "month",
            ):
                warnings.append(
                    _(
                        "Work entries may not be generated for the period "
                        "from %(start)s to %(end)s.",
                        start=date_utils.add(
                            date_utils.end_of(
                                fields.Date.today(),
                                "month",
                            ),
                            days=1,
                        ),
                        end=slip.date_to,
                    )
                )

            # La validación de duración de Odoo no aplica a liquidaciones.
            if not slip._cr_is_settlement_structure():
                schedule = (
                    slip.contract_id.schedule_pay
                    or slip.contract_id.structure_type_id.default_schedule_pay
                )

                if (
                    schedule
                    and slip.date_from + slip._get_schedule_timedelta()
                    != slip.date_to
                ):
                    warnings.append(
                        _(
                            "The duration of the payslip is not accurate "
                            "according to the structure type."
                        )
                    )

            if warnings:
                warnings = [
                    _("This payslip can be erroneous :")
                ] + warnings

                slip.warning_message = "\n  ・ ".join(warnings)

    @api.depends(
        "date_from",
        "date_to",
        "struct_id",
    )
    def _compute_is_wrong_duration(self):
        """
        Las liquidaciones laborales son recibos especiales de un solo día,
        por lo que no deben marcarse como de duración incorrecta.
        """
        for slip in self:
            if slip._cr_is_settlement_structure():
                slip.is_wrong_duration = False
                continue

            slip.is_wrong_duration = bool(
                slip.date_to
                and (
                    slip.contract_id.schedule_pay
                    or slip.contract_id.structure_type_id.default_schedule_pay
                )
                and (
                    slip.date_from + slip._get_schedule_timedelta()
                    != slip.date_to
                )
            )

    def _cr_expected_structure_from_run(self):
        self.ensure_one()
        run = self.payslip_run_id
        if not run or not run.cr_process_type or run.cr_process_type == "ordinary":
            return self.env["hr.payroll.structure"]

        xmlid_by_process = {
            "aguinaldo": "l10n_cr_hr.structure_aguinaldo",
            "extraordinary": "l10n_cr_hr.structure_extraordinary",
            "settlement": "l10n_cr_hr.structure_settlement",
        }
        xmlid = xmlid_by_process.get(run.cr_process_type)
        return self.env.ref(xmlid, raise_if_not_found=False) if xmlid else self.env["hr.payroll.structure"]

    @api.model
    def _cr_find_approved_termination_for_values(self, vals):
        """
        Busca una liquidación aprobada únicamente cuando la fecha de
        terminación cae dentro del período del recibo.

        Esto evita que un recibo de un período posterior capture una
        liquidación anterior.
        """
        employee_id = vals.get("employee_id")
        if not employee_id:
            return self.env["cr.payroll.termination"]

        date_from = vals.get("date_from")
        date_to = vals.get("date_to")

        if date_from:
            date_from = fields.Date.to_date(date_from)
        if date_to:
            date_to = fields.Date.to_date(date_to)

        domain = [
            ("employee_id", "=", employee_id),
            ("state", "=", "approved"),
            ("payslip_id", "=", False),
        ]

        if date_from:
            domain.append(("termination_date", ">=", date_from))
        if date_to:
            domain.append(("termination_date", "<=", date_to))

        company_id = vals.get("company_id")
        if company_id:
            domain.append(("company_id", "=", company_id))

        return self.env["cr.payroll.termination"].search(
            domain,
            order="termination_date desc, id desc",
            limit=1,
        )

    @api.model
    def _cr_normalize_settlement_values(self, vals, termination):
        """
        Fuerza los datos críticos de un recibo de liquidación a coincidir
        con la liquidación aprobada que lo origina.
        """
        if not termination:
            return vals

        vals["cr_termination_id"] = termination.id
        vals["employee_id"] = termination.employee_id.id
        vals["contract_id"] = termination.contract_id.id
        vals["company_id"] = termination.company_id.id
        vals["date_from"] = termination.termination_date
        vals["date_to"] = termination.termination_date
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        Run = self.env["hr.payslip.run"]
        settlement_structure = self.env.ref(
            "l10n_cr_hr.structure_settlement",
            raise_if_not_found=False,
        )

        xmlid_by_process = {
            "aguinaldo": "l10n_cr_hr.structure_aguinaldo",
            "extraordinary": "l10n_cr_hr.structure_extraordinary",
            "settlement": "l10n_cr_hr.structure_settlement",
        }

        for vals in vals_list:
            run_id = vals.get("payslip_run_id")
            run = Run.browse(run_id).exists() if run_id else Run

            if run and run.cr_process_type != "ordinary":
                structure = self.env.ref(
                    xmlid_by_process.get(run.cr_process_type),
                    raise_if_not_found=False,
                )
                if not structure:
                    raise UserError(
                        _("No se encontró la estructura salarial correspondiente al tipo de proceso del lote.")
                    )
                vals["struct_id"] = structure.id

            is_settlement = bool(
                settlement_structure
                and vals.get("struct_id") == settlement_structure.id
            )

            if is_settlement:
                termination = self.env["cr.payroll.termination"]
                termination_id = vals.get("cr_termination_id")

                if termination_id:
                    termination = self.env["cr.payroll.termination"].browse(
                        termination_id
                    ).exists()
                    if not termination:
                        raise UserError(_("La liquidación laboral indicada no existe."))
                    if termination.state != "approved":
                        raise UserError(
                            _("Solo una liquidación aprobada puede vincularse a un recibo.")
                        )
                else:
                    termination = self._cr_find_approved_termination_for_values(vals)

                if not termination:
                    raise UserError(
                        _(
                            "No existe una liquidación aprobada y pendiente de procesar "
                            "para este empleado cuya fecha de terminación pertenezca al "
                            "período del recibo. La estructura 'CR - Liquidación laboral' "
                            "no puede utilizarse como un recibo manual sin una liquidación aprobada."
                        )
                    )

                self._cr_normalize_settlement_values(vals, termination)

        slips = super().create(vals_list)

        for slip in slips.filtered("cr_termination_id"):
            termination = slip.cr_termination_id
            termination.with_context(cr_allow_termination_write=True).write({
                "payslip_id": slip.id,
                "payslip_run_id": slip.payslip_run_id.id or False,
            })

        return slips

    def compute_sheet(self):
        settlement_structure = self.env.ref(
            "l10n_cr_hr.structure_settlement",
            raise_if_not_found=False,
        )

        for slip in self:
            expected = slip._cr_expected_structure_from_run()
            if expected and slip.struct_id != expected:
                slip.struct_id = expected

            if settlement_structure and slip.struct_id == settlement_structure:
                termination = slip.cr_termination_id

                if not termination:
                    termination = slip._cr_find_approved_termination_for_values({
                        "employee_id": slip.employee_id.id,
                        "company_id": slip.company_id.id,
                        "date_from": slip.date_from,
                        "date_to": slip.date_to,
                    })

                    if not termination:
                        raise UserError(
                            _(
                                "Este recibo utiliza 'CR - Liquidación laboral', pero no existe "
                                "una liquidación aprobada pendiente para %s cuya fecha de "
                                "terminación pertenezca al período %s - %s."
                            )
                            % (
                                slip.employee_id.display_name,
                                slip.date_from,
                                slip.date_to,
                            )
                        )

                    slip.cr_termination_id = termination

                if termination.state not in ("approved", "paid"):
                    raise UserError(
                        _(
                            "La liquidación vinculada a este recibo debe estar aprobada "
                            "antes de calcular la hoja."
                        )
                    )

                values_to_fix = {}
                if slip.employee_id != termination.employee_id:
                    values_to_fix["employee_id"] = termination.employee_id.id
                if slip.contract_id != termination.contract_id:
                    values_to_fix["contract_id"] = termination.contract_id.id
                if slip.company_id != termination.company_id:
                    values_to_fix["company_id"] = termination.company_id.id
                if slip.date_from != termination.termination_date:
                    values_to_fix["date_from"] = termination.termination_date
                if slip.date_to != termination.termination_date:
                    values_to_fix["date_to"] = termination.termination_date

                if values_to_fix:
                    slip.write(values_to_fix)

                termination.with_context(cr_allow_termination_write=True).write({
                    "payslip_id": slip.id,
                    "payslip_run_id": slip.payslip_run_id.id or False,
                })

                # Sincronizar siempre los inputs de liquidación antes de calcular.
                # La liquidación aprobada es la fuente de verdad; el recibo solo
                # transporta esos importes a las reglas salariales.
                values = termination._prepare_payslip_input_values()
                InputType = self.env["hr.payslip.input.type"]
                Input = self.env["hr.payslip.input"]

                for code, amount in values.items():
                    input_type = InputType.search([
                        ("code", "=", code),
                    ], limit=1)

                    if not input_type:
                        continue

                    existing = slip.input_line_ids.filtered(
                        lambda line: line.input_type_id == input_type
                    )[:1]

                    if existing:
                        existing.amount = amount
                    else:
                        Input.create({
                            "payslip_id": slip.id,
                            "input_type_id": input_type.id,
                            "amount": amount,
                        })

        return super().compute_sheet()

    @api.depends("line_ids.total", "line_ids.code", "line_ids.category_id.code", "date_to", "employee_id")
    def _compute_cr_dashboard_amounts(self):
        for slip in self:
            lines = slip.line_ids

            def amount_by_codes(*codes):
                code_set = set(codes)
                return sum(lines.filtered(lambda line: line.code in code_set).mapped("total"))

            def amount_by_categories(*codes):
                category_set = set(codes)
                return sum(lines.filtered(lambda line: line.category_id.code in category_set).mapped("total"))

            basic = amount_by_codes("BASIC", "CR_BASIC", "CR_BASIC_BIWEEKLY", "CR_BASIC_WEEKLY", "CR_BASIC_HOURLY")
            if not basic:
                basic = amount_by_categories("BASIC")

            gross = amount_by_codes("GROSS", "CR_GROSS")
            if not gross:
                gross = amount_by_categories("GROSS")

            employee_ccss = abs(amount_by_codes("CR_SEM_EMP", "CR_IVM_EMP", "CR_BP_EMP"))
            income_tax = abs(amount_by_codes("CR_RENTA"))
            recurring = abs(amount_by_codes("CR_RECUR_DED"))

            category_deductions = abs(amount_by_categories("EMPLOYEE_SOC", "TAX", "LEGAL_DED", "VOL_DED"))
            total_deductions = category_deductions or abs(sum(
                line.total for line in lines
                if line.total < 0 and line.category_id.code not in {"NET", "EMPLOYER_SOC", "PROVISION"}
            ))

            net = amount_by_codes("NET", "CR_NET")
            if not net:
                net = amount_by_categories("NET")

            employer_social = amount_by_categories("EMPLOYER_SOC")
            aguinaldo_provision = amount_by_codes("CR_AGUINALDO_PROV", "CR_PROV_AGUINALDO", "CR_AGUINALDO_PROVISION")
            vacation_provision = amount_by_codes("CR_VACATION_PROV", "CR_PROV_VACATION", "CR_VACATION_PROVISION")

            if not aguinaldo_provision or not vacation_provision:
                provision_lines = lines.filtered(lambda line: line.category_id.code == "PROVISION")
                for line in provision_lines:
                    code_name = (line.code or "").upper()
                    line_name = (line.name or "").upper()
                    if not aguinaldo_provision and ("AGUINALDO" in code_name or "AGUINALDO" in line_name):
                        aguinaldo_provision += line.total
                    elif not vacation_provision and ("VAC" in code_name or "VACACION" in line_name):
                        vacation_provision += line.total

            slip.cr_basic_total = basic
            slip.cr_gross_total = gross
            slip.cr_employee_ccss_total = employee_ccss
            slip.cr_income_tax_total = income_tax
            slip.cr_recurring_deduction_total = recurring
            slip.cr_total_deductions = total_deductions
            slip.cr_net_total = net
            slip.cr_employer_social_total = employer_social
            slip.cr_aguinaldo_period_total = aguinaldo_provision
            slip.cr_vacation_provision_total = vacation_provision
            slip.cr_employer_cost_total = gross + employer_social + aguinaldo_provision + vacation_provision
            slip.cr_aguinaldo_accumulated = slip._cr_compute_aguinaldo() if slip.employee_id and slip.date_to else 0.0

    def _compute_cr_validation_message(self):
        WorkEntry = self.env["hr.work.entry"].sudo()

        for slip in self:
            issues = []
            contract = slip.contract_id
            usage = getattr(slip.struct_id, "cr_structure_usage", False)
            is_special = usage in ("aguinaldo", "extraordinary", "termination", "settlement")

            if not contract:
                issues.append("Empleado sin contrato en el recibo.")
            else:
                if contract.wage <= 0:
                    issues.append("El salario contractual debe ser mayor que cero.")

                if not is_special and not contract.resource_calendar_id:
                    issues.append("El contrato no tiene horario laboral.")

                if not is_special:
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
                                % (
                                    days,
                                    dict(contract._fields["cr_pay_frequency"].selection).get(
                                        contract.cr_pay_frequency
                                    ),
                                )
                            )

            if not slip.employee_id.identification_id:
                issues.append("Falta identificación del empleado.")
            if not slip.employee_id.bank_account_id:
                issues.append("Falta cuenta bancaria del empleado.")
            if slip.date_from and slip.date_to and slip.date_from > slip.date_to:
                issues.append("El período del recibo es inválido.")

            if usage == "termination":
                if not slip.cr_termination_id:
                    issues.append("El recibo de liquidación no está vinculado a una liquidación aprobada.")
                elif slip.cr_termination_id.state not in ("approved", "paid"):
                    issues.append("La liquidación vinculada no está aprobada.")

            if contract and slip.date_from and slip.date_to and not is_special:
                missing = slip._cr_missing_disability_configuration()
                if missing:
                    issues.append(
                        "Falta configurar una regla activa para: %s."
                        % ", ".join(missing)
                    )

                attendance_hours = slip._cr_worked_hours(
                    ["WORK100", "WORK", "ATTENDANCE"]
                )
                period_days = (slip.date_to - slip.date_from).days + 1

                if attendance_hours > period_days * 24.0:
                    issues.append(
                        "Las entradas de trabajo muestran %.2f horas en %s días; "
                        "regenere las entradas del período."
                        % (attendance_hours, period_days)
                    )

                domain = [
                    ("employee_id", "=", slip.employee_id.id),
                    (
                        "date_start",
                        "<=",
                        fields.Datetime.to_string(
                            fields.Datetime.to_datetime(slip.date_to).replace(
                                hour=23,
                                minute=59,
                                second=59,
                            )
                        ),
                    ),
                    ("date_stop", ">=", fields.Datetime.to_datetime(slip.date_from)),
                ]
                work_entries = WorkEntry.search(domain)
                if "state" in WorkEntry._fields:
                    bad_states = work_entries.filtered(
                        lambda entry: entry.state in ("draft", "conflict")
                    )
                    if bad_states:
                        issues.append(
                            "Existen entradas de trabajo en borrador o conflicto dentro del período."
                        )

            duplicate_domain = [
                ("id", "!=", slip.id),
                ("employee_id", "=", slip.employee_id.id),
                ("date_from", "=", slip.date_from),
                ("date_to", "=", slip.date_to),
                ("state", "not in", ["cancel"]),
            ]
            if slip.struct_id:
                duplicate_domain.append(("struct_id", "=", slip.struct_id.id))

            duplicate = self.search_count(duplicate_domain)
            if slip.employee_id and duplicate:
                issues.append(
                    "Ya existe otro recibo para el mismo empleado, período y estructura salarial."
                )

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

    def _cr_disability_mapping(self):
        """Mapa entre código de entrada de trabajo, regla CR y tipo de ausencia.

        Lactancia no se incluye aquí porque es una reducción remunerada de
        jornada y nunca debe procesarse como incapacidad o rebajo salarial.
        """
        return {
            "CR_SICK_CCSS": (
                "CCSS",
                "l10n_cr_hr.leave_type_cr_ccss",
            ),
            "CR_SICK_INS": (
                "INS",
                "l10n_cr_hr.leave_type_cr_ins",
            ),
            "CR_SICK_SOA": (
                "SOA",
                "l10n_cr_hr.leave_type_cr_soa",
            ),
            "CR_MATERNITY": (
                "MATERNITY",
                "l10n_cr_hr.leave_type_cr_maternity",
            ),
            "CR_PATERNITY": (
                "PATERNITY",
                "l10n_cr_hr.leave_type_cr_paternity",
            ),
            "CR_ADOPTION": (
                "ADOPTION",
                "l10n_cr_hr.leave_type_cr_adoption",
            ),
            "CR_MATERNAL_DEATH": (
                "MATERNAL_DEATH",
                "l10n_cr_hr.leave_type_cr_maternal_death",
            ),
            "CR_CARE_TERMINAL": (
                "CARE_TERMINAL",
                "l10n_cr_hr.leave_type_cr_terminal_care",
            ),
            "CR_CARE_MINOR_SEVERE": (
                "CARE_MINOR_SEVERE",
                "l10n_cr_hr.leave_type_cr_seriously_ill_minor",
            ),
            "CR_CARE_EXTRAORDINARY": (
                "CARE_EXTRAORDINARY",
                "l10n_cr_hr.leave_type_cr_extraordinary_care",
            ),
        }

    def _cr_disability_leaves(self, leave_type):
        """Ausencias validadas que se cruzan con el período del recibo."""
        self.ensure_one()

        if (
            not leave_type
            or not self.employee_id
            or not self.date_from
            or not self.date_to
        ):
            return self.env["hr.leave"]

        return self.env["hr.leave"].sudo().search([
            ("employee_id", "=", self.employee_id.id),
            ("holiday_status_id", "=", leave_type.id),
            ("state", "=", "validate"),
            ("request_date_from", "<=", self.date_to),
            ("request_date_to", ">=", self.date_from),
        ], order="request_date_from,id")

    def _cr_disability_profiles(self):
        """
        Retorna perfiles de incapacidad usando días calendario reales.

        Los work entries solo representan días/horas laborables. No deben usarse
        para decidir si una incapacidad se encuentra en el día 1, 2, 3, 4, etc.
        """
        self.ensure_one()

        profiles = []
        Rule = self.env["cr.payroll.disability.rule"].sudo()
        slip_from = fields.Date.to_date(self.date_from)
        slip_to = fields.Date.to_date(self.date_to)

        for work_code, (rule_code, leave_xmlid) in self._cr_disability_mapping().items():
            leave_type = self.env.ref(
                leave_xmlid,
                raise_if_not_found=False,
            )
            if not leave_type:
                continue

            leaves = self._cr_disability_leaves(leave_type)
            if not leaves:
                continue

            calendar_days = 0.0

            for leave in leaves:
                leave_from = fields.Date.to_date(
                    leave.request_date_from or leave.date_from
                )
                leave_to = fields.Date.to_date(
                    leave.request_date_to or leave.date_to
                )

                overlap_from = max(leave_from, slip_from)
                overlap_to = min(leave_to, slip_to)

                if overlap_from <= overlap_to:
                    calendar_days += (
                        overlap_to - overlap_from
                    ).days + 1

            rules = Rule.search([
                ("code", "=", rule_code),
                ("active", "=", True),
                ("date_from", "<=", self.date_to),
                "|",
                ("date_to", "=", False),
                ("date_to", ">=", self.date_from),
                "|",
                ("company_id", "=", self.company_id.id),
                ("company_id", "=", False),
            ], order="company_id desc, day_from,id")

            profiles.append(
                (
                    work_code,
                    rule_code,
                    calendar_days,
                    rules,
                )
            )

        return profiles

    def _cr_missing_disability_configuration(self):
        self.ensure_one()
        missing = []
        for _work_code, rule_code, _days, rules in self._cr_disability_profiles():
            if not rules:
                missing.append(rule_code)
        return sorted(set(missing))

    def _cr_disability_amounts(self):
        """
        Calcula incapacidad por día calendario real del período médico.

        Mantiene la posición real dentro de la ausencia aunque cruce fines de
        semana o una nueva quincena. Ejemplo viernes-martes:
        viernes=1, sábado=2, domingo=3, lunes=4, martes=5.
        """
        self.ensure_one()

        result = {
            "deduction": 0.0,
            "employer_taxable": 0.0,
            "employer_nontaxable": 0.0,
            "subsidy_advance": 0.0,
            "subsidy_info": 0.0,
        }

        if (
            not self.employee_id
            or not self.date_from
            or not self.date_to
        ):
            return result

        Rule = self.env["cr.payroll.disability.rule"].sudo()
        day_value = self._cr_day_value()
        slip_from = fields.Date.to_date(self.date_from)
        slip_to = fields.Date.to_date(self.date_to)

        processed_days = set()

        for _work_code, (rule_code, leave_xmlid) in self._cr_disability_mapping().items():
            leave_type = self.env.ref(
                leave_xmlid,
                raise_if_not_found=False,
            )
            if not leave_type:
                continue

            leaves = self._cr_disability_leaves(leave_type)
            if not leaves:
                continue

            candidate_rules = Rule.search([
                ("code", "=", rule_code),
                ("active", "=", True),
                ("date_from", "<=", self.date_to),
                "|",
                ("date_to", "=", False),
                ("date_to", ">=", self.date_from),
                "|",
                ("company_id", "=", self.company_id.id),
                ("company_id", "=", False),
            ], order="company_id desc, day_from,id")

            for leave in leaves:
                leave_from = fields.Date.to_date(
                    leave.request_date_from or leave.date_from
                )
                leave_to = fields.Date.to_date(
                    leave.request_date_to or leave.date_to
                )

                overlap_from = max(leave_from, slip_from)
                overlap_to = min(leave_to, slip_to)

                if overlap_from > overlap_to:
                    continue

                current = overlap_from

                while current <= overlap_to:
                    unique_key = (
                        rule_code,
                        current,
                    )

                    if unique_key in processed_days:
                        current += date_utils.relativedelta(days=1)
                        continue

                    processed_days.add(unique_key)

                    day_position = (
                        current - leave_from
                    ).days + 1

                    matching_rules = candidate_rules.filtered(
                        lambda r: (
                            r.day_from <= day_position
                            and (
                                not r.day_to
                                or day_position <= r.day_to
                            )
                            and r.date_from <= current
                            and (
                                not r.date_to
                                or current <= r.date_to
                            )
                        )
                    )

                    if matching_rules:
                        rule = matching_rules.sorted(
                            key=lambda r: (
                                0
                                if r.company_id == self.company_id
                                else 1,
                                r.day_from,
                                r.id,
                            )
                        )[:1]

                        if rule:
                            rule = rule[0]
                            base = day_value

                            result["deduction"] += (
                                base
                                * rule.deduction_rate
                                / 100.0
                            )

                            employer = (
                                base
                                * rule.employer_rate
                                / 100.0
                            )

                            if rule.employer_payment_taxable:
                                result["employer_taxable"] += employer
                            else:
                                result["employer_nontaxable"] += employer

                            subsidy = (
                                base
                                * rule.subsidy_rate
                                / 100.0
                            )

                            result["subsidy_info"] += subsidy

                            if rule.subsidy_paid_in_payroll:
                                result["subsidy_advance"] += subsidy

                    current += date_utils.relativedelta(days=1)

        return {
            key: self._cr_round(value)
            for key, value in result.items()
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

        # Acumula otros recibos del mismo mes ya hechos/pagados para evitar
        # duplicar la exención mensual, pero excluye estructuras especiales
        # que no deben contaminar la base mensual ordinaria de renta.
        month_start = self.date_to.replace(day=1)

        excluded_structures = self.env["hr.payroll.structure"]

        for xmlid in (
            "l10n_cr_hr.structure_aguinaldo",
            "l10n_cr_hr.structure_settlement",
        ):
            structure = self.env.ref(
                xmlid,
                raise_if_not_found=False,
            )
            if structure:
                excluded_structures |= structure

        domain = [
            ("id", "!=", self.id),
            ("employee_id", "=", self.employee_id.id),
            ("date_to", ">=", month_start),
            ("date_to", "<=", self.date_to),
            ("state", "in", ["done", "paid"]),
        ]

        if excluded_structures:
            domain.append(
                ("struct_id", "not in", excluded_structures.ids)
            )

        prior = self.search(domain)

        prior_taxable = sum(
            payslip._cr_taxable_gross_estimate()
            for payslip in prior
        )

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

    def _cr_disability_provision_adjustment(self, benefit):
        """Monto institucional que debe conservar derechos laborales.

        Algunas licencias, como maternidad, tienen una parte pagada por la
        institución (CCSS) que no entra al GROSS ordinario del recibo, pero sí
        debe conservar la base para aguinaldo y/o vacaciones cuando la regla
        legal correspondiente así lo indique.
        """
        self.ensure_one()

        if benefit not in ("aguinaldo", "vacation"):
            return 0.0

        if (
            not self.employee_id
            or not self.date_from
            or not self.date_to
        ):
            return 0.0

        flag_name = (
            "affects_aguinaldo"
            if benefit == "aguinaldo"
            else "affects_vacation"
        )

        Rule = self.env["cr.payroll.disability.rule"].sudo()
        slip_from = fields.Date.to_date(self.date_from)
        slip_to = fields.Date.to_date(self.date_to)
        day_value = self._cr_day_value()

        adjustment = 0.0
        processed_days = set()

        for _work_code, (rule_code, leave_xmlid) in (
            self._cr_disability_mapping().items()
        ):
            leave_type = self.env.ref(
                leave_xmlid,
                raise_if_not_found=False,
            )
            if not leave_type:
                continue

            leaves = self._cr_disability_leaves(leave_type)
            if not leaves:
                continue

            candidate_rules = Rule.search([
                ("code", "=", rule_code),
                ("active", "=", True),
                ("date_from", "<=", self.date_to),
                "|",
                ("date_to", "=", False),
                ("date_to", ">=", self.date_from),
                "|",
                ("company_id", "=", self.company_id.id),
                ("company_id", "=", False),
            ], order="company_id desc, day_from,id")

            for leave in leaves:
                leave_from = fields.Date.to_date(
                    leave.request_date_from or leave.date_from
                )
                leave_to = fields.Date.to_date(
                    leave.request_date_to or leave.date_to
                )

                overlap_from = max(leave_from, slip_from)
                overlap_to = min(leave_to, slip_to)

                if overlap_from > overlap_to:
                    continue

                current = overlap_from

                while current <= overlap_to:
                    unique_key = (rule_code, current)

                    if unique_key in processed_days:
                        current += date_utils.relativedelta(days=1)
                        continue

                    processed_days.add(unique_key)

                    day_position = (current - leave_from).days + 1

                    matching_rules = candidate_rules.filtered(
                        lambda r: (
                            r.day_from <= day_position
                            and (
                                not r.day_to
                                or day_position <= r.day_to
                            )
                            and r.date_from <= current
                            and (
                                not r.date_to
                                or current <= r.date_to
                            )
                        )
                    )

                    if matching_rules:
                        rule = matching_rules.sorted(
                            key=lambda r: (
                                0
                                if r.company_id == self.company_id
                                else 1,
                                r.day_from,
                                r.id,
                            )
                        )[:1]

                        if rule:
                            rule = rule[0]

                            if getattr(rule, flag_name, False):
                                adjustment += (
                                    day_value
                                    * rule.subsidy_rate
                                    / 100.0
                                )

                    current += date_utils.relativedelta(days=1)

        return self._cr_round(adjustment)

    def _cr_aguinaldo_provision_base(self, gross):
        """Base de provisión de aguinaldo incluyendo licencias protegidas."""
        self.ensure_one()
        return self._cr_round(
            max(gross or 0.0, 0.0)
            + self._cr_disability_provision_adjustment("aguinaldo")
        )

    def _cr_vacation_provision_base(self, gross):
        """Base de provisión de vacaciones incluyendo licencias protegidas."""
        self.ensure_one()
        return self._cr_round(
            max(gross or 0.0, 0.0)
            + self._cr_disability_provision_adjustment("vacation")
        )

    def _cr_has_maternity_in_period(self):
        """Indica si el recibo se cruza con una licencia de maternidad válida."""
        self.ensure_one()

        leave_type = self.env.ref(
            "l10n_cr_hr.leave_type_cr_maternity",
            raise_if_not_found=False,
        )
        if not leave_type:
            return False

        return bool(self._cr_disability_leaves(leave_type))

    def _cr_has_bmc_exempt_legal_leave_in_period(self):
        """Ausencias que suspenden/reparten salario y no deben forzar BMC.

        Maternidad reparte la remuneración entre patrono/CCSS. SOA y las
        licencias de cuido de Ley 7756 suspenden el salario ordinario y tienen
        prestaciones institucionales externas. En esos casos SEM/IVM sobre el
        salario realmente a cargo del patrono no debe inflarse artificialmente
        por la BMC dentro de este recibo.
        """
        self.ensure_one()

        xmlids = (
            "l10n_cr_hr.leave_type_cr_maternity",
            "l10n_cr_hr.leave_type_cr_soa",
            "l10n_cr_hr.leave_type_cr_terminal_care",
            "l10n_cr_hr.leave_type_cr_seriously_ill_minor",
            "l10n_cr_hr.leave_type_cr_extraordinary_care",
        )

        for xmlid in xmlids:
            leave_type = self.env.ref(
                xmlid,
                raise_if_not_found=False,
            )
            if leave_type and self._cr_disability_leaves(leave_type):
                return True

        return False


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
            # Excepciones CCSS a la Base Mínima Contributiva:
            # - ingreso de un trabajador en un período intermedio del mes;
            # - salida/cesantía en un período intermedio del mes.
            #
            # En esos casos SEM/IVM se calculan sobre el salario realmente
            # reportado y NO se eleva la base hasta la BMC.
            contract = self.contract_id
            contract_start = (
                fields.Date.to_date(contract.date_start)
                if contract and contract.date_start
                else False
            )
            contract_end = (
                fields.Date.to_date(contract.date_end)
                if contract and contract.date_end
                else False
            )

            month_end_day = calendar.monthrange(
                self.date_to.year,
                self.date_to.month,
            )[1]
            month_end = self.date_to.replace(day=month_end_day)

            intermediate_entry = bool(
                contract_start
                and month_start < contract_start <= self.date_to
            )
            intermediate_exit = bool(
                contract_end
                and month_start <= contract_end < month_end
                and contract_end <= self.date_to
            )

            # Durante licencia de maternidad no se eleva artificialmente la
            # mitad patronal hasta la BMC. El componente patronal del recibo
            # se calcula sobre la porción efectivamente a cargo del patrono.
            bmc_exempt_legal_leave = (
                self._cr_has_bmc_exempt_legal_leave_in_period()
            )

            if (
                not intermediate_entry
                and not intermediate_exit
                and not bmc_exempt_legal_leave
            ):
                monthly_minimum = max(
                    Param.value_at(
                        minimum_code,
                        self.date_to,
                        self.company_id,
                    ) or 0.0,
                    0.0,
                )

                # Para trabajadores activos durante el mes, la BMC se lleva
                # acumulada proporcionalmente al avance del mes. Esto evita
                # cobrar la BMC mensual completa en la primera quincena.
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


    def _cr_basic_biweekly_amount(self):
        """
        Salario básico para nómina quincenal.

        Regla CR:
        - Si el contrato cubre toda la quincena, paga salario mensual / 2.
        - Si el contrato inicia o termina dentro de la quincena, prorratea
          únicamente por los días calendario efectivamente cubiertos por
          el contrato, usando salario mensual / divisor diario (30 por
          defecto).

        Importante:
        Este helper NO rebaja ausencias, incapacidades, tardías ni permisos.
        Esos conceptos se procesan mediante sus reglas específicas para evitar
        duplicar rebajos.
        """
        self.ensure_one()

        contract = self.contract_id
        if not contract or not self.date_from or not self.date_to:
            return 0.0

        wage = max(contract.wage or 0.0, 0.0)
        if not wage:
            return 0.0

        date_from = fields.Date.to_date(self.date_from)
        date_to = fields.Date.to_date(self.date_to)

        contract_start = (
            fields.Date.to_date(contract.date_start)
            if contract.date_start
            else date_from
        )
        contract_end = (
            fields.Date.to_date(contract.date_end)
            if contract.date_end
            else date_to
        )

        active_from = max(date_from, contract_start)
        active_to = min(date_to, contract_end)

        if active_from > active_to:
            return 0.0

        # Contrato activo durante todo el período: media mensualidad.
        if active_from == date_from and active_to == date_to:
            return self._cr_round(wage / 2.0)

        # Alta o baja dentro de la quincena: salario diario × días calendario.
        divisor = contract.cr_days_divisor or 30.0
        if divisor <= 0:
            divisor = 30.0

        payable_days = (active_to - active_from).days + 1
        daily_wage = wage / divisor

        return self._cr_round(daily_wage * payable_days)

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
        return self._cr_round(max(total / 12.0, 0.0))
