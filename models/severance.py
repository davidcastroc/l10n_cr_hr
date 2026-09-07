# -*- coding: utf-8 -*-

from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class CrPayrollTermination(models.Model):
    _name = "cr.payroll.termination"
    _description = "Liquidación laboral Costa Rica"
    _order = "termination_date desc, id desc"

    name = fields.Char(
        string="Nombre",
        required=True,
        default="Liquidación",
        copy=False,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado",
        required=True,
        index=True,
    )
    contract_id = fields.Many2one(
        "hr.contract",
        string="Contrato",
        required=True,
        domain="[('employee_id', '=', employee_id)]",
        index=True,
    )
    company_id = fields.Many2one(
        related="employee_id.company_id",
        string="Compañía",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Moneda",
        store=True,
        readonly=True,
    )
    termination_date = fields.Date(
        string="Fecha de terminación",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    reason = fields.Selection(
        [
            ("resignation", "Renuncia"),
            ("dismissal_with_liability", "Despido con responsabilidad"),
            ("dismissal_without_liability", "Despido sin responsabilidad"),
            ("mutual", "Mutuo acuerdo"),
            ("contract_end", "Finalización de contrato"),
            ("death", "Fallecimiento"),
            ("other", "Otro"),
        ],
        string="Motivo",
        required=True,
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("review", "En revisión"),
            ("approved", "Aprobada"),
            ("paid", "Pagada"),
            ("cancel", "Cancelada"),
        ],
        string="Estado",
        default="draft",
        required=True,
        copy=False,
        index=True,
    )
    notes = fields.Text(string="Notas")

    include_notice = fields.Boolean(
        string="Incluir preaviso",
        help="Incluye la indemnización por preaviso dentro de la liquidación.",
    )
    include_severance = fields.Boolean(
        string="Incluir cesantía",
        help="Incluye el auxilio de cesantía dentro de la liquidación.",
    )

    service_years = fields.Integer(string="Años de servicio", readonly=True, copy=False)
    service_months = fields.Integer(string="Meses adicionales", readonly=True, copy=False)
    service_days = fields.Integer(string="Días adicionales", readonly=True, copy=False)
    salary_average = fields.Monetary(
        string="Promedio salarial últimos 6 meses",
        readonly=True,
        copy=False,
    )
    daily_salary = fields.Monetary(
        string="Salario diario de referencia",
        readonly=True,
        copy=False,
    )
    notice_days = fields.Float(string="Días de preaviso", readonly=True, copy=False)
    severance_days = fields.Float(string="Días de cesantía", readonly=True, copy=False)

    pending_salary = fields.Monetary(string="Salario pendiente")
    pending_commissions = fields.Monetary(string="Comisiones pendientes")
    pending_overtime = fields.Monetary(string="Horas extra pendientes")
    vacation_days = fields.Float(string="Días de vacaciones")
    vacation_amount = fields.Monetary(string="Vacaciones", copy=False)
    aguinaldo_amount = fields.Monetary(string="Aguinaldo proporcional", copy=False)
    notice_amount = fields.Monetary(string="Preaviso", copy=False)
    severance_amount = fields.Monetary(string="Cesantía", copy=False)
    other_income = fields.Monetary(string="Otros ingresos")
    deductions = fields.Monetary(string="Deducciones")

    gross_total = fields.Monetary(
        string="Total bruto",
        compute="_compute_totals",
        store=True,
    )
    net_total = fields.Monetary(
        string="Total neto",
        compute="_compute_totals",
        store=True,
    )

    payslip_id = fields.Many2one(
        "hr.payslip",
        string="Recibo de liquidación",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    payslip_run_id = fields.Many2one(
        "hr.payslip.run",
        string="Lote de liquidación",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    submitted_by_id = fields.Many2one("res.users", string="Enviado a revisión por", readonly=True, copy=False)
    submitted_date = fields.Datetime(string="Fecha de envío a revisión", readonly=True, copy=False)
    approved_by_id = fields.Many2one("res.users", string="Aprobado por", readonly=True, copy=False)
    approved_date = fields.Datetime(string="Fecha de aprobación", readonly=True, copy=False)
    paid_by_id = fields.Many2one("res.users", string="Marcado como pagado por", readonly=True, copy=False)
    paid_date = fields.Datetime(string="Fecha de pago", readonly=True, copy=False)
    cancelled_by_id = fields.Many2one("res.users", string="Cancelado por", readonly=True, copy=False)
    cancelled_date = fields.Datetime(string="Fecha de cancelación", readonly=True, copy=False)

    @api.depends(
        "pending_salary",
        "pending_commissions",
        "pending_overtime",
        "vacation_amount",
        "aguinaldo_amount",
        "include_notice",
        "notice_amount",
        "include_severance",
        "severance_amount",
        "other_income",
        "deductions",
    )
    def _compute_totals(self):
        for rec in self:
            gross = (
                (rec.pending_salary or 0.0)
                + (rec.pending_commissions or 0.0)
                + (rec.pending_overtime or 0.0)
                + (rec.vacation_amount or 0.0)
                + (rec.aguinaldo_amount or 0.0)
                + ((rec.notice_amount or 0.0) if rec.include_notice else 0.0)
                + ((rec.severance_amount or 0.0) if rec.include_severance else 0.0)
                + (rec.other_income or 0.0)
            )
            rec.gross_total = gross
            rec.net_total = gross - (rec.deductions or 0.0)

    @api.onchange("employee_id", "termination_date")
    def _onchange_employee_contract(self):
        for rec in self:
            if not rec.employee_id:
                rec.contract_id = False
                continue

            domain = [("employee_id", "=", rec.employee_id.id)]
            if rec.termination_date:
                domain += [
                    ("date_start", "<=", rec.termination_date),
                    "|",
                    ("date_end", "=", False),
                    ("date_end", ">=", rec.termination_date),
                ]

            contract = self.env["hr.contract"].search(
                domain,
                order="date_start desc, id desc",
                limit=1,
            )
            if contract:
                rec.contract_id = contract

    @api.onchange("reason")
    def _onchange_reason(self):
        for rec in self:
            if rec.reason == "dismissal_with_liability":
                rec.include_notice = True
                rec.include_severance = True
            elif rec.reason == "death":
                rec.include_notice = False
                rec.include_severance = True
            elif rec.reason in (
                "resignation",
                "dismissal_without_liability",
                "contract_end",
            ):
                rec.include_notice = False
                rec.include_severance = False

    @api.onchange(
        "contract_id",
        "termination_date",
        "vacation_days",
        "include_notice",
        "include_severance",
    )
    def _onchange_recalculate(self):
        for rec in self:
            if (
                rec.contract_id
                and rec.employee_id
                and rec.termination_date
                and rec.state in ("draft", "review")
            ):
                values = rec._prepare_calculation_values()
                for key, value in values.items():
                    setattr(rec, key, value)

    def _get_service_delta(self):
        self.ensure_one()
        if (
            not self.contract_id
            or not self.contract_id.date_start
            or not self.termination_date
        ):
            return relativedelta()
        return relativedelta(self.termination_date, self.contract_id.date_start)

    def _get_salary_average(self):
        self.ensure_one()
        if not self.employee_id or not self.termination_date:
            return 0.0

        start_date = self.termination_date - relativedelta(months=6)
        domain = [
            ("employee_id", "=", self.employee_id.id),
            ("date_to", "<=", self.termination_date),
            ("date_to", ">", start_date),
            ("state", "in", ["done", "paid"]),
        ]
        if self.contract_id:
            domain.append(("contract_id", "=", self.contract_id.id))

        slips = self.env["hr.payslip"].search(domain, order="date_from asc, id asc")
        monthly_gross = defaultdict(float)

        for slip in slips:
            gross = slip.line_ids.filtered(lambda line: line.code in ("GROSS", "CR_GROSS"))[:1]
            amount = gross.total if gross else slip.cr_gross_total
            if not amount:
                continue
            key = (slip.date_to.year, slip.date_to.month)
            monthly_gross[key] += abs(amount)

        amounts = list(monthly_gross.values())
        if amounts:
            return sum(amounts) / len(amounts)

        return self.contract_id.wage or 0.0

    def _get_daily_salary(self, monthly_average):
        self.ensure_one()
        divisor = getattr(self.contract_id, "cr_days_divisor", 30.0) or 30.0
        if divisor <= 0:
            divisor = 30.0
        return (monthly_average or 0.0) / divisor

    def _get_notice_days(self):
        self.ensure_one()
        delta = self._get_service_delta()
        total_months = delta.years * 12 + delta.months

        if total_months < 3:
            return 0.0
        if total_months < 6:
            return 7.0
        if total_months == 6 and not delta.days:
            return 7.0
        if delta.years < 1:
            return 15.0
        return 30.0

    @api.model
    def _get_severance_rate_for_year(self, year):
        table = {
            1: 19.50,
            2: 20.00,
            3: 20.50,
            4: 21.00,
            5: 21.24,
            6: 21.50,
            7: 22.00,
            8: 22.00,
            9: 22.00,
            10: 21.50,
            11: 21.00,
            12: 20.50,
        }
        return 20.00 if year >= 13 else table.get(year, 0.0)

    def _get_severance_days(self):
        self.ensure_one()
        delta = self._get_service_delta()
        total_months = delta.years * 12 + delta.months

        if total_months < 3:
            return 0.0

        if delta.years < 1:
            if total_months < 6 or (total_months == 6 and not delta.days):
                return 7.0
            return 14.0

        completed_years = delta.years
        fraction_over_six_months = (
            delta.months > 6
            or (delta.months == 6 and delta.days > 0)
        )
        payable_years = completed_years + (1 if fraction_over_six_months else 0)
        payable_years = min(payable_years, 8)

        return self._get_severance_rate_for_year(completed_years) * payable_years

    def _get_regular_period_start(self):
        """
        Determina el inicio del período ordinario que contiene la fecha de terminación.
        Para salarios mensuales/quincenales se usa calendario natural.
        """
        self.ensure_one()

        if not self.termination_date:
            return False

        termination = fields.Date.to_date(self.termination_date)
        frequency = getattr(self.contract_id, "cr_pay_frequency", False) or "monthly"

        if frequency == "biweekly":
            day = 1 if termination.day <= 15 else 16
            return termination.replace(day=day)

        if frequency == "weekly":
            # Semana natural de nómina: lunes a domingo.
            return termination - relativedelta(days=termination.weekday())

        # Mensual, por horas y cualquier frecuencia no reconocida:
        # usar inicio de mes como límite seguro.
        return termination.replace(day=1)

    def _get_pending_salary_amount(self):
        """
        Calcula salario ordinario pendiente hasta la fecha de terminación.

        Evita duplicar períodos ya pagados/finalizados. Para contratos con salario
        mensual de referencia usa salario diario = wage / divisor (30 por defecto).
        En modalidad por horas no se inventan horas: queda en cero para revisión
        manual, ya que requiere horas efectivamente trabajadas.
        """
        self.ensure_one()

        if not self.employee_id or not self.contract_id or not self.termination_date:
            return 0.0

        termination = fields.Date.to_date(self.termination_date)
        period_start = self._get_regular_period_start()
        if not period_start:
            return 0.0

        if self.contract_id.date_start:
            period_start = max(
                period_start,
                fields.Date.to_date(self.contract_id.date_start),
            )

        frequency = getattr(self.contract_id, "cr_pay_frequency", False) or "monthly"

        # Para salario por horas se requiere información efectiva de horas.
        if frequency == "hourly" or getattr(self.contract_id, "cr_salary_mode", False) == "hourly":
            return 0.0

        regular_structures = self.env["hr.payroll.structure"].search([
            ("cr_is_regular_payroll", "=", True),
        ])

        paid_slips = self.env["hr.payslip"].search([
            ("employee_id", "=", self.employee_id.id),
            ("contract_id", "=", self.contract_id.id),
            ("state", "in", ["done", "paid"]),
            ("struct_id", "in", regular_structures.ids),
            ("date_to", ">=", period_start),
            ("date_from", "<=", termination),
        ], order="date_to desc, id desc")

        # Si ya existe un recibo ordinario finalizado que llega hasta la terminación,
        # no hay salario pendiente por este período.
        if paid_slips and any(slip.date_to >= termination for slip in paid_slips):
            return 0.0

        # Si una parte del período ya fue pagada, empezar al día siguiente.
        if paid_slips:
            latest_paid_to = max(slip.date_to for slip in paid_slips)
            period_start = max(
                period_start,
                latest_paid_to + relativedelta(days=1),
            )

        if period_start > termination:
            return 0.0

        divisor = getattr(self.contract_id, "cr_days_divisor", 30.0) or 30.0
        if divisor <= 0:
            divisor = 30.0

        daily_wage = (self.contract_id.wage or 0.0) / divisor
        payable_days = (termination - period_start).days + 1

        return max(daily_wage * payable_days, 0.0)

    def _get_vacation_days_balance(self):
        """
        Saldo de vacaciones validado a la fecha de terminación:
        asignaciones aprobadas menos vacaciones aprobadas/consumidas.

        Se restringe a tipos cuyo nombre contiene 'Vacaciones', que corresponde
        al tipo CR usado por esta localización.
        """
        self.ensure_one()

        if not self.employee_id or not self.termination_date:
            return 0.0

        VacationType = self.env["hr.leave.type"]
        vacation_types = VacationType.search([
            ("name", "ilike", "Vacaciones"),
        ])

        if not vacation_types:
            return 0.0

        allocations = self.env["hr.leave.allocation"].search([
            ("employee_id", "=", self.employee_id.id),
            ("holiday_status_id", "in", vacation_types.ids),
            ("state", "=", "validate"),
        ])

        allocated_days = sum(allocations.mapped("number_of_days"))

        leaves = self.env["hr.leave"].search([
            ("employee_id", "=", self.employee_id.id),
            ("holiday_status_id", "in", vacation_types.ids),
            ("state", "=", "validate"),
            ("date_from", "<=", fields.Datetime.to_datetime(self.termination_date)),
        ])

        used_days = sum(leaves.mapped("number_of_days"))

        return max(allocated_days - used_days, 0.0)

    def _get_aguinaldo_amount(self, extra_earnings=0.0):
        self.ensure_one()
        if not self.employee_id or not self.contract_id or not self.termination_date:
            return 0.0

        dummy = self.env["hr.payslip"].new({
            "employee_id": self.employee_id.id,
            "contract_id": self.contract_id.id,
            "company_id": self.company_id.id,
            "date_from": self.termination_date,
            "date_to": self.termination_date,
        })
        method = getattr(dummy, "_cr_compute_aguinaldo", False)
        base_aguinaldo = (method() or 0.0) if method else 0.0

        # El salario/comisiones/horas extra que se pagan dentro de la propia
        # liquidación también son salario devengado para aguinaldo.
        return base_aguinaldo + max(extra_earnings or 0.0, 0.0) / 12.0

    def _get_vacation_amount(self):
        self.ensure_one()
        if not self.contract_id:
            return 0.0

        divisor = getattr(self.contract_id, "cr_days_divisor", 30.0) or 30.0
        if divisor <= 0:
            divisor = 30.0

        return (self.vacation_days or 0.0) * (self.contract_id.wage or 0.0) / divisor

    def _prepare_calculation_values(self):
        self.ensure_one()
        if not self.employee_id or not self.contract_id or not self.termination_date:
            return {}

        delta = self._get_service_delta()
        salary_average = self._get_salary_average()
        daily_salary = self._get_daily_salary(salary_average)
        notice_days = self._get_notice_days() if self.include_notice else 0.0
        severance_days = self._get_severance_days() if self.include_severance else 0.0

        pending_salary = self._get_pending_salary_amount()
        vacation_days = self._get_vacation_days_balance()

        divisor = getattr(self.contract_id, "cr_days_divisor", 30.0) or 30.0
        if divisor <= 0:
            divisor = 30.0

        vacation_amount = (
            vacation_days * (self.contract_id.wage or 0.0) / divisor
        )

        extra_earnings_for_aguinaldo = (
            pending_salary
            + (self.pending_commissions or 0.0)
            + (self.pending_overtime or 0.0)
        )

        return {
            "service_years": delta.years,
            "service_months": delta.months,
            "service_days": delta.days,
            "salary_average": salary_average,
            "daily_salary": daily_salary,
            "notice_days": notice_days,
            "severance_days": severance_days,
            "pending_salary": pending_salary,
            "vacation_days": vacation_days,
            "vacation_amount": vacation_amount,
            "aguinaldo_amount": self._get_aguinaldo_amount(
                extra_earnings=extra_earnings_for_aguinaldo
            ),
            "notice_amount": (
                daily_salary * notice_days
                if self.include_notice
                else 0.0
            ),
            "severance_amount": (
                daily_salary * severance_days
                if self.include_severance
                else 0.0
            ),
        }

    def _validate_basic_data(self):
        self.ensure_one()

        if not self.employee_id:
            raise ValidationError(_("Debe seleccionar un empleado."))
        if not self.contract_id:
            raise ValidationError(_("Debe seleccionar un contrato."))
        if not self.termination_date:
            raise ValidationError(_("Debe indicar la fecha de terminación."))
        if not self.reason:
            raise ValidationError(_("Debe seleccionar el motivo de terminación."))
        if self.contract_id.employee_id != self.employee_id:
            raise ValidationError(_("El contrato seleccionado no pertenece al empleado indicado."))
        if self.contract_id.date_start and self.termination_date < self.contract_id.date_start:
            raise ValidationError(_("La fecha de terminación no puede ser anterior al inicio del contrato."))

    def action_recalculate(self):
        for rec in self:
            if rec.state not in ("draft", "review"):
                raise ValidationError(
                    _("Solo se puede recalcular una liquidación en Borrador o En revisión.")
                )
            rec._validate_basic_data()
            rec.with_context(cr_allow_termination_write=True).write(
                rec._prepare_calculation_values()
            )
        return True

    def action_submit_review(self):
        for rec in self:
            if rec.state != "draft":
                raise ValidationError(_("Solo una liquidación en Borrador puede enviarse a revisión."))
            rec._validate_basic_data()
            rec.action_recalculate()
            rec.with_context(cr_allow_termination_write=True).write({
                "state": "review",
                "submitted_by_id": self.env.user.id,
                "submitted_date": fields.Datetime.now(),
            })
        return True

    def action_reset_draft(self):
        for rec in self:
            if rec.state != "review":
                raise ValidationError(_("Solo una liquidación En revisión puede volver a Borrador."))
            rec.with_context(cr_allow_termination_write=True).write({
                "state": "draft",
                "submitted_by_id": False,
                "submitted_date": False,
            })
        return True

    def action_approve(self):
        for rec in self:
            if rec.state != "review":
                raise ValidationError(_("La liquidación debe estar En revisión antes de aprobarse."))

            rec._validate_basic_data()

            # Congelar siempre el cálculo más reciente al momento de aprobar.
            calculation_values = rec._prepare_calculation_values()
            calculation_values.update({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_date": fields.Datetime.now(),
            })

            rec.with_context(cr_allow_termination_write=True).write(
                calculation_values
            )
        return True

    def _prepare_payslip_input_values(self):
        self.ensure_one()
        return {
            "CR_SETTLEMENT_SALARY": self.pending_salary or 0.0,
            "CR_SETTLEMENT_COMMISSIONS": self.pending_commissions or 0.0,
            "CR_SETTLEMENT_OVERTIME": self.pending_overtime or 0.0,
            "CR_SETTLEMENT_VACATION": self.vacation_amount or 0.0,
            "CR_SETTLEMENT_AGUINALDO": self.aguinaldo_amount or 0.0,
            "CR_NOTICE": self.notice_amount if self.include_notice else 0.0,
            "CR_SEVERANCE": self.severance_amount if self.include_severance else 0.0,
            "CR_SETTLEMENT_OTHER": self.other_income or 0.0,
            "CR_SETTLEMENT_DEDUCTIONS": self.deductions or 0.0,
        }

    def action_generate_payslip(self):
        """
        Genera el recibo real desde una liquidación aprobada.
        No se vuelve a calcular la liquidación en el recibo: se transfieren
        exactamente los importes aprobados.
        """
        self.ensure_one()

        if self.state != "approved":
            raise UserError(_("Solo una liquidación aprobada puede generar un recibo."))

        if self.payslip_id and self.payslip_id.state != "cancel":
            slip = self.payslip_id

            expected_values = {
                "employee_id": self.employee_id.id,
                "contract_id": self.contract_id.id,
                "date_from": self.termination_date,
                "date_to": self.termination_date,
                "cr_termination_id": self.id,
            }

            needs_fix = (
                slip.employee_id != self.employee_id
                or slip.contract_id != self.contract_id
                or slip.date_from != self.termination_date
                or slip.date_to != self.termination_date
                or slip.cr_termination_id != self
            )

            if slip.state in ("done", "paid"):
                if needs_fix:
                    raise UserError(
                        _(
                            "El recibo existente de esta liquidación está finalizado/pagado "
                            "pero sus datos no coinciden con la fecha de terminación. "
                            "Debe corregirse mediante el procedimiento contable correspondiente."
                        )
                    )
            else:
                if needs_fix:
                    slip.write(expected_values)

                # Aunque el recibo ya exista y sus vínculos estén correctos,
                # recalcular siempre para reflejar los importes aprobados actuales.
                slip.compute_sheet()

            return {
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip",
                "view_mode": "form",
                "res_id": slip.id,
                "target": "current",
            }

        structure = self.env.ref("l10n_cr_hr.structure_settlement", raise_if_not_found=False)
        if not structure:
            raise UserError(_("No se encontró la estructura 'CR - Liquidación laboral'."))

        run = self.env["hr.payslip.run"].with_context(cr_allow_settlement_process=True).create({
            "name": _("Liquidación - %s - %s") % (
                self.employee_id.name,
                fields.Date.to_string(self.termination_date),
            ),
            "date_start": self.termination_date,
            "date_end": self.termination_date,
            "cr_process_type": "settlement",
        })

        slip = self.env["hr.payslip"].create({
            "name": _("Liquidación - %s") % self.employee_id.name,
            "employee_id": self.employee_id.id,
            "contract_id": self.contract_id.id,
            "struct_id": structure.id,
            "payslip_run_id": run.id,
            "date_from": self.termination_date,
            "date_to": self.termination_date,
            "company_id": self.company_id.id,
            "cr_termination_id": self.id,
        })
        slip.compute_sheet()

        self.with_context(cr_allow_termination_write=True).write({
            "payslip_id": slip.id,
            "payslip_run_id": run.id,
        })

        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.payslip",
            "view_mode": "form",
            "res_id": slip.id,
            "target": "current",
        }

    def action_open_payslip(self):
        self.ensure_one()
        if not self.payslip_id:
            raise UserError(_("Esta liquidación todavía no tiene un recibo generado."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.payslip",
            "view_mode": "form",
            "res_id": self.payslip_id.id,
            "target": "current",
        }

    def action_mark_paid(self):
        for rec in self:
            if rec.state != "approved":
                raise ValidationError(_("Solo una liquidación Aprobada puede marcarse como Pagada."))

            if rec.payslip_id and rec.payslip_id.state not in ("paid", "done"):
                raise ValidationError(
                    _(
                        "El recibo de liquidación todavía no está finalizado/pagado. "
                        "Procese primero el recibo de nómina."
                    )
                )

            rec.with_context(cr_allow_termination_write=True).write({
                "state": "paid",
                "paid_by_id": self.env.user.id,
                "paid_date": fields.Datetime.now(),
            })
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state not in ("draft", "review"):
                raise ValidationError(
                    _("Solo una liquidación en Borrador o En revisión puede cancelarse.")
                )
            rec.with_context(cr_allow_termination_write=True).write({
                "state": "cancel",
                "cancelled_by_id": self.env.user.id,
                "cancelled_date": fields.Datetime.now(),
            })
        return True

    @api.constrains("termination_date", "contract_id", "employee_id")
    def _check_contract_data(self):
        for rec in self:
            if rec.contract_id and rec.employee_id and rec.contract_id.employee_id != rec.employee_id:
                raise ValidationError(_("El contrato seleccionado no pertenece al empleado."))
            if (
                rec.contract_id
                and rec.contract_id.date_start
                and rec.termination_date
                and rec.termination_date < rec.contract_id.date_start
            ):
                raise ValidationError(_("La terminación no puede ser anterior al inicio del contrato."))

    @api.constrains(
        "vacation_days",
        "pending_salary",
        "pending_commissions",
        "pending_overtime",
        "other_income",
        "deductions",
    )
    def _check_non_negative_values(self):
        for rec in self:
            if rec.vacation_days < 0:
                raise ValidationError(_("Los días de vacaciones no pueden ser negativos."))

            for field_name in (
                "pending_salary",
                "pending_commissions",
                "pending_overtime",
                "other_income",
                "deductions",
            ):
                if rec[field_name] < 0:
                    raise ValidationError(
                        _("El campo '%s' no puede ser negativo.")
                        % rec._fields[field_name].string
                    )

    def write(self, vals):
        protected = {
            "employee_id",
            "contract_id",
            "termination_date",
            "reason",
            "include_notice",
            "include_severance",
            "pending_salary",
            "pending_commissions",
            "pending_overtime",
            "vacation_days",
            "vacation_amount",
            "aguinaldo_amount",
            "notice_amount",
            "severance_amount",
            "other_income",
            "deductions",
            "salary_average",
            "daily_salary",
            "notice_days",
            "severance_days",
        }

        if not self.env.context.get("cr_allow_termination_write"):
            for rec in self:
                if rec.state in ("approved", "paid") and protected.intersection(vals):
                    raise ValidationError(
                        _("Una liquidación aprobada o pagada no puede modificarse directamente.")
                    )

        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state not in ("draft", "cancel"):
                raise ValidationError(
                    _("Solo pueden eliminarse liquidaciones en Borrador o Canceladas.")
                )
        return super().unlink()
