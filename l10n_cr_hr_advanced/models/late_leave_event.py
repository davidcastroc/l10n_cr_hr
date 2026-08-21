# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CrPayrollLateLeaveEvent(models.Model):
    _name = "cr.payroll.late.leave.event"
    _description = "Evento tardío de ausencia o incapacidad CR"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "received_date desc, id desc"

    name = fields.Char(
        string="Referencia",
        required=True,
        default="Evento tardío",
        tracking=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado",
        required=True,
        tracking=True,
    )
    contract_id = fields.Many2one(
        "hr.contract",
        string="Contrato",
        required=True,
        domain="[('employee_id', '=', employee_id)]",
    )
    rule_code = fields.Selection([
        ("CCSS", "Incapacidad CCSS"),
        ("INS", "Incapacidad INS"),
        ("MATERNITY", "Licencia de maternidad"),
        ("PATERNITY", "Licencia de paternidad"),
    ], string="Tratamiento legal", required=True, tracking=True)
    leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Tipo de ausencia o incapacidad",
        required=True,
    )
    date_from = fields.Date(string="Fecha inicial", required=True)
    date_to = fields.Date(string="Fecha final", required=True)
    received_date = fields.Date(
        string="Fecha de recepción",
        required=True,
        default=fields.Date.context_today,
    )
    document_number = fields.Char(
        string="Número de documento",
        required=True,
        copy=False,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="Documentos de respaldo",
    )

    daily_salary = fields.Monetary(
        string="Salario diario de referencia",
        currency_field="currency_id",
        compute="_compute_daily_salary",
        store=True,
        readonly=False,
        help="Se obtiene del contrato usando su divisor configurado. Puede ajustarse únicamente si existe una razón documentada.",
    )
    currency_id = fields.Many2one(
        related="employee_id.company_id.currency_id",
        string="Moneda",
        store=True,
    )

    total_days = fields.Integer(
        string="Días calendario",
        compute="_compute_amounts",
        store=True,
    )
    employer_amount = fields.Monetary(
        string="Monto patronal según reglas vigentes",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    external_subsidy_amount = fields.Monetary(
        string="Subsidio institucional informativo",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    legal_rule_summary = fields.Text(
        string="Reglas legales aplicadas",
        compute="_compute_amounts",
        store=True,
    )

    overlapping_leave_ids = fields.Many2many(
        "hr.leave",
        "cr_late_event_overlap_leave_rel",
        "event_id",
        "leave_id",
        string="Ausencias superpuestas",
        readonly=True,
    )
    closed_payslip_ids = fields.Many2many(
        "hr.payslip",
        "cr_late_event_closed_slip_rel",
        "event_id",
        "payslip_id",
        string="Recibos cerrados afectados",
        readonly=True,
    )
    generated_leave_id = fields.Many2one(
        "hr.leave",
        string="Ausencia generada",
        readonly=True,
        copy=False,
    )
    incident_ids = fields.One2many(
        "cr.payroll.incident",
        "late_leave_event_id",
        string="Ajustes de nómina generados",
        readonly=True,
    )

    state = fields.Selection([
        ("draft", "Borrador"),
        ("reviewed", "Revisado"),
        ("applied", "Aplicado"),
        ("cancel", "Cancelado"),
    ], string="Estado", default="draft", tracking=True)

    operator_id = fields.Many2one(
        "res.users",
        string="Registrado por",
        default=lambda self: self.env.user,
        readonly=True,
    )
    approved_by_id = fields.Many2one(
        "res.users",
        string="Aplicado por",
        readonly=True,
        copy=False,
    )
    applied_at = fields.Datetime(
        string="Fecha de aplicación",
        readonly=True,
        copy=False,
    )
    administrative_self_approval = fields.Boolean(
        string="Autoaprobación administrativa",
        readonly=True,
        copy=False,
    )

    _sql_constraints = [
        (
            "document_number_unique",
            "unique(document_number)",
            "El número de documento ya fue utilizado en otro evento tardío.",
        ),
    ]

    def _is_system_administrator(self):
        self.ensure_one()
        return self.env.user.has_group("base.group_system")

    @api.depends("contract_id", "contract_id.wage")
    def _compute_daily_salary(self):
        for rec in self:
            if not rec.contract_id:
                rec.daily_salary = 0.0
                continue
            contract = rec.contract_id
            if getattr(contract, "cr_salary_mode", False) == "daily":
                rec.daily_salary = contract.wage
            else:
                divisor = getattr(contract, "cr_days_divisor", False) or 30.0
                rec.daily_salary = contract.wage / divisor if divisor else 0.0

    def _active_rules(self):
        self.ensure_one()
        Rule = self.env["cr.payroll.disability.rule"].sudo()
        return Rule.search([
            ("code", "=", self.rule_code),
            ("active", "=", True),
            ("date_from", "<=", self.date_to),
            "|", ("date_to", "=", False), ("date_to", ">=", self.date_from),
            "|", ("company_id", "=", self.employee_id.company_id.id),
                 ("company_id", "=", False),
        ], order="company_id desc, day_from")

    def _rule_for_day(self, day_number, day_date):
        self.ensure_one()
        Rule = self.env["cr.payroll.disability.rule"].sudo()
        rules = Rule.search([
            ("code", "=", self.rule_code),
            ("active", "=", True),
            ("date_from", "<=", day_date),
            "|", ("date_to", "=", False), ("date_to", ">=", day_date),
            "|", ("company_id", "=", self.employee_id.company_id.id),
                 ("company_id", "=", False),
        ], order="company_id desc, day_from")
        for rule in rules:
            if day_number < rule.day_from:
                continue
            if rule.day_to and day_number > rule.day_to:
                continue
            return rule
        return Rule.browse()

    def _amounts_for_range(self, range_from, range_to):
        self.ensure_one()
        employer = subsidy = 0.0
        cursor = range_from
        while cursor <= range_to:
            day_number = (cursor - self.date_from).days + 1
            rule = self._rule_for_day(day_number, cursor)
            if not rule:
                raise ValidationError(_(
                    "No existe una regla legal activa de %(code)s para el día %(date)s "
                    "y la compañía %(company)s.",
                    code=self.rule_code,
                    date=cursor,
                    company=self.employee_id.company_id.display_name,
                ))
            employer += self.daily_salary * (rule.employer_rate or 0.0) / 100.0
            subsidy += self.daily_salary * (rule.subsidy_rate or 0.0) / 100.0
            cursor += timedelta(days=1)
        return employer, subsidy

    @api.depends(
        "date_from",
        "date_to",
        "daily_salary",
        "rule_code",
        "employee_id.company_id",
    )
    def _compute_amounts(self):
        for rec in self:
            if (
                not rec.date_from
                or not rec.date_to
                or rec.date_to < rec.date_from
                or not rec.rule_code
            ):
                rec.total_days = 0
                rec.employer_amount = 0.0
                rec.external_subsidy_amount = 0.0
                rec.legal_rule_summary = False
                continue

            rec.total_days = (rec.date_to - rec.date_from).days + 1

            try:
                employer, subsidy = rec._amounts_for_range(
                    rec.date_from,
                    rec.date_to,
                )
            except ValidationError:
                employer = subsidy = 0.0

            rec.employer_amount = employer
            rec.external_subsidy_amount = subsidy

            rules = rec._active_rules()
            rec.legal_rule_summary = "\n".join(
                "%s | días %s-%s | patrono %.4f%% | subsidio %.4f%% | vigente %s a %s"
                % (
                    rule.name,
                    rule.day_from,
                    rule.day_to or "sin límite",
                    rule.employer_rate or 0.0,
                    rule.subsidy_rate or 0.0,
                    rule.date_from,
                    rule.date_to or "sin límite",
                )
                for rule in rules
            )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError(
                    _("La fecha final no puede ser anterior a la fecha inicial.")
                )

    def action_review(self):
        for rec in self:
            if not rec.attachment_ids:
                raise ValidationError(
                    _("Debe adjuntar el documento de respaldo.")
                )
            if rec.daily_salary <= 0:
                raise ValidationError(
                    _("El salario diario de referencia debe ser mayor que cero.")
                )
            # Falla explícitamente si la parametrización legal está incompleta.
            rec._amounts_for_range(rec.date_from, rec.date_to)

            overlaps = self.env["hr.leave"].sudo().search([
                ("employee_id", "=", rec.employee_id.id),
                ("state", "in", ["confirm", "validate1", "validate"]),
                ("request_date_from", "<=", rec.date_to),
                ("request_date_to", ">=", rec.date_from),
            ])

            slips = self.env["hr.payslip"].sudo().search([
                ("employee_id", "=", rec.employee_id.id),
                ("state", "in", ["done", "paid"]),
                ("date_from", "<=", rec.date_to),
                ("date_to", ">=", rec.date_from),
            ])

            rec.write({
                "overlapping_leave_ids": [(6, 0, overlaps.ids)],
                "closed_payslip_ids": [(6, 0, slips.ids)],
                "state": "reviewed",
            })

        return True

    def _refuse_overlapping_leaves(self):
        for rec in self:
            for leave in rec.overlapping_leave_ids:
                if leave.state in ("validate", "validate1", "confirm"):
                    try:
                        leave.sudo().action_refuse()
                    except Exception:
                        leave.sudo().write({"state": "refuse"})

    def _create_new_leave(self):
        self.ensure_one()
        leave = self.env["hr.leave"].sudo().create({
            "name": "Evento tardío %s - %s" % (
                self.document_number,
                self.employee_id.name,
            ),
            "employee_id": self.employee_id.id,
            "holiday_status_id": self.leave_type_id.id,
            "request_date_from": self.date_from,
            "request_date_to": self.date_to,
        })
        try:
            leave.action_validate()
        except Exception:
            # Algunos tipos requieren una secuencia de aprobación; el registro
            # queda creado para completar ese flujo nativo.
            pass
        return leave

    def _create_closed_period_adjustments(self):
        Incident = self.env["cr.payroll.incident"].sudo()

        for rec in self:
            for slip in rec.closed_payslip_ids:
                overlap_from = max(rec.date_from, slip.date_from)
                overlap_to = min(rec.date_to, slip.date_to)
                if overlap_to < overlap_from:
                    continue

                employer_amount, _subsidy = rec._amounts_for_range(
                    overlap_from,
                    overlap_to,
                )
                if abs(employer_amount) < 0.005:
                    continue

                existing = Incident.search([
                    ("late_leave_event_id", "=", rec.id),
                    ("retroactive_origin_period", "=", "%s a %s" % (
                        slip.date_from, slip.date_to
                    )),
                    ("state", "not in", ["cancel", "rejected"]),
                ], limit=1)
                if existing:
                    continue

                Incident.create({
                    "name": "Ajuste evento tardío %s - %s" % (
                        rec.document_number,
                        slip.name,
                    ),
                    "employee_id": rec.employee_id.id,
                    "contract_id": rec.contract_id.id,
                    "date": rec.received_date,
                    "incident_type": "late_leave_adjustment",
                    "quantity": 1.0,
                    "rate": employer_amount,
                    "amount": employer_amount,
                    "description": (
                        "Corrección de período cerrado %s a %s por evento tardío "
                        "%s. El importe se obtiene de las reglas de incapacidad "
                        "vigentes configuradas en Nómina Costa Rica."
                        % (
                            slip.date_from,
                            slip.date_to,
                            rec.document_number,
                        )
                    ),
                    "state": "approved",
                    "late_leave_event_id": rec.id,
                    "retroactive_origin_period": "%s a %s" % (
                        slip.date_from,
                        slip.date_to,
                    ),
                })

    def action_apply(self):
        for rec in self:
            if rec.state != "reviewed":
                raise ValidationError(
                    _("Primero debe revisar el evento tardío.")
                )

            is_admin = rec._is_system_administrator()
            if rec.operator_id == self.env.user and not is_admin:
                raise ValidationError(_(
                    "Por control interno, quien registra el evento no puede aplicarlo. "
                    "Un Administrador del sistema sí puede realizar ambas acciones."
                ))

            rec._refuse_overlapping_leaves()

            if not rec.generated_leave_id:
                rec.generated_leave_id = rec._create_new_leave()

            rec._create_closed_period_adjustments()

            rec.write({
                "state": "applied",
                "approved_by_id": self.env.user.id,
                "applied_at": fields.Datetime.now(),
                "administrative_self_approval": bool(
                    is_admin and rec.operator_id == self.env.user
                ),
            })

        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == "applied":
                raise ValidationError(
                    _("Un evento aplicado no puede cancelarse sin una reversión formal.")
                )
            rec.state = "cancel"
        return True
