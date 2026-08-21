# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CrPayrollRetroactiveAdjustment(models.Model):
    _name = "cr.payroll.retroactive.adjustment"
    _description = "Ajuste retroactivo de nómina Costa Rica"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "target_date desc, id desc"

    name = fields.Char(
        string="Referencia",
        required=True,
        default="Ajuste retroactivo",
        tracking=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado",
        required=True,
        index=True,
        tracking=True,
    )
    contract_id = fields.Many2one(
        "hr.contract",
        string="Contrato",
        required=True,
        domain="[('employee_id', '=', employee_id)]",
    )
    company_id = fields.Many2one(
        related="employee_id.company_id",
        string="Compañía",
        store=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Moneda",
        store=True,
    )

    origin_date_from = fields.Date(string="Desde período origen", required=True)
    origin_date_to = fields.Date(string="Hasta período origen", required=True)
    target_date = fields.Date(
        string="Fecha de nómina complementaria",
        required=True,
        default=fields.Date.context_today,
        help="Fecha en la que se incorporará la diferencia a la nómina. Los cálculos legales de la nómina se resuelven por el motor principal de Nómina Costa Rica.",
    )
    old_wage = fields.Monetary(
        string="Salario anterior",
        required=True,
        currency_field="currency_id",
    )
    new_wage = fields.Monetary(
        string="Salario nuevo",
        required=True,
        currency_field="currency_id",
    )
    reason = fields.Text(string="Motivo", required=True)
    attachment_ids = fields.Many2many("ir.attachment", string="Evidencia")

    line_ids = fields.One2many(
        "cr.payroll.retroactive.adjustment.line",
        "adjustment_id",
        string="Diferencias",
    )
    amount_total = fields.Monetary(
        string="Diferencia bruta total",
        compute="_compute_total",
        store=True,
        currency_field="currency_id",
    )

    state = fields.Selection([
        ("draft", "Borrador"),
        ("calculated", "Calculado"),
        ("approved", "Aprobado"),
        ("generated", "Complementaria generada"),
        ("cancel", "Cancelado"),
    ], string="Estado", default="draft", required=True, tracking=True)

    operator_id = fields.Many2one(
        "res.users",
        string="Preparado por",
        default=lambda self: self.env.user,
        readonly=True,
        copy=False,
        tracking=True,
    )
    approved_by_id = fields.Many2one(
        "res.users",
        string="Aprobado por",
        readonly=True,
        copy=False,
    )
    approved_at = fields.Datetime(
        string="Fecha de aprobación",
        readonly=True,
        copy=False,
    )
    administrative_self_approval = fields.Boolean(
        string="Autoaprobación administrativa",
        readonly=True,
        copy=False,
        help="Se activa cuando un Administrador del sistema prepara y aprueba el mismo registro.",
    )

    external_report_required = fields.Boolean(
        string="Requiere gestión en reporte externo",
        default=False,
        tracking=True,
        help="Use este control únicamente cuando el proceso de la compañía requiera una declaración o reporte externo relacionado.",
    )
    external_report_state = fields.Selection([
        ("pending", "Pendiente"),
        ("reported", "Reportado"),
        ("not_required", "No requerido"),
    ], string="Estado de reporte externo", default="not_required", tracking=True)
    external_report_notes = fields.Text(string="Notas de reporte externo")
    external_reported_by_id = fields.Many2one(
        "res.users",
        string="Reportado por",
        readonly=True,
        copy=False,
    )
    external_reported_at = fields.Datetime(
        string="Fecha de reporte externo",
        readonly=True,
        copy=False,
    )

    incident_ids = fields.Many2many(
        "cr.payroll.incident",
        string="Incidencias generadas",
        compute="_compute_incident_ids",
        readonly=True,
    )

    @api.depends("line_ids.difference", "line_ids.include")
    def _compute_total(self):
        for rec in self:
            rec.amount_total = sum(
                rec.line_ids.filtered("include").mapped("difference")
            )

    def _compute_incident_ids(self):
        Incident = self.env["cr.payroll.incident"].sudo()
        for rec in self:
            rec.incident_ids = Incident.search([
                ("retroactive_adjustment_id", "=", rec.id),
            ])

    @api.constrains("origin_date_from", "origin_date_to", "old_wage", "new_wage")
    def _check_values(self):
        for rec in self:
            if rec.origin_date_to < rec.origin_date_from:
                raise ValidationError(_("El período origen es inválido."))
            if rec.old_wage <= 0 or rec.new_wage <= 0:
                raise ValidationError(_("Los salarios deben ser mayores que cero."))

    def _is_system_administrator(self):
        self.ensure_one()
        return self.env.user.has_group("base.group_system")

    def _policy_for_line(self, line):
        self.ensure_one()
        Policy = self.env["cr.payroll.retroactive.rule.policy"].sudo()
        policy = Policy.search([
            ("company_id", "=", self.company_id.id),
            ("salary_rule_id", "=", line.salary_rule_id.id),
            ("active", "=", True),
        ], limit=1)
        if policy:
            return policy.policy

        # Comportamiento seguro por defecto:
        # - salario básico y horas extra se consideran dependientes del salario.
        # - los demás conceptos se excluyen hasta que la empresa los configure.
        category = (line.category_id.code or "").upper()
        code = (line.code or "").upper()
        if category in {"BASIC", "OVERTIME"}:
            return "proportional_wage"
        if code in {
            "BASIC", "CR_BASIC", "CR_BASIC_BIWEEKLY",
            "CR_BASIC_WEEKLY", "CR_BASIC_HOURLY",
            "CR_OT_15", "CR_OT_20", "CR_OT_30",
        }:
            return "proportional_wage"
        return "exclude"

    def action_calculate(self):
        Line = self.env["cr.payroll.retroactive.adjustment.line"].sudo()

        for rec in self:
            if rec.state not in ("draft", "calculated"):
                raise ValidationError(
                    _("Solo puede recalcular un ajuste en borrador o calculado.")
                )

            rec.line_ids.unlink()

            slips = self.env["hr.payslip"].sudo().search([
                ("employee_id", "=", rec.employee_id.id),
                ("state", "in", ["done", "paid"]),
                ("date_to", ">=", rec.origin_date_from),
                ("date_from", "<=", rec.origin_date_to),
            ], order="date_from,id")

            if not slips:
                raise ValidationError(
                    _("No existen recibos cerrados en el período origen.")
                )

            ratio = rec.new_wage / rec.old_wage

            for slip in slips:
                for salary_line in slip.line_ids.filtered(lambda l: bool(l.total)):
                    policy = rec._policy_for_line(salary_line)
                    if policy == "exclude":
                        continue
                    if policy == "fixed":
                        recalculated = salary_line.total
                    else:
                        recalculated = salary_line.total * ratio

                    difference = recalculated - salary_line.total
                    if abs(difference) < 0.005:
                        continue

                    Line.create({
                        "adjustment_id": rec.id,
                        "payslip_id": slip.id,
                        "origin_date_from": slip.date_from,
                        "origin_date_to": slip.date_to,
                        "salary_rule_id": salary_line.salary_rule_id.id,
                        "salary_rule_code": salary_line.code,
                        "concept_name": salary_line.name,
                        "policy": policy,
                        "original_amount": salary_line.total,
                        "recalculated_amount": recalculated,
                        "include": True,
                    })

            if not rec.line_ids:
                raise ValidationError(_(
                    "No se encontraron conceptos configurados para recálculo retroactivo. "
                    "Revise las políticas de recálculo por regla salarial."
                ))

            rec.state = "calculated"

        return True

    def action_approve(self):
        for rec in self:
            if rec.state != "calculated":
                raise ValidationError(
                    _("El ajuste debe estar calculado antes de aprobarse.")
                )

            is_admin = rec._is_system_administrator()
            if rec.operator_id == self.env.user and not is_admin:
                raise ValidationError(_(
                    "Por control interno, quien prepara el retroactivo no puede aprobarlo. "
                    "Un Administrador del sistema sí puede realizar ambas acciones y quedará auditado."
                ))

            if not rec.line_ids.filtered("include"):
                raise ValidationError(_("No hay diferencias seleccionadas para aprobar."))
            if not rec.reason:
                raise ValidationError(_("Debe indicar el motivo del retroactivo."))
            if not rec.attachment_ids:
                raise ValidationError(_("Debe adjuntar evidencia del cambio retroactivo."))

            rec.write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_at": fields.Datetime.now(),
                "administrative_self_approval": bool(
                    is_admin and rec.operator_id == self.env.user
                ),
            })

        return True

    def action_generate_complementary(self):
        Incident = self.env["cr.payroll.incident"].sudo()

        for rec in self:
            if rec.state != "approved":
                raise ValidationError(
                    _("El ajuste debe estar aprobado antes de generar la complementaria.")
                )

            existing = Incident.search([
                ("retroactive_adjustment_id", "=", rec.id),
                ("state", "not in", ["cancel", "rejected"]),
            ])
            if existing:
                raise ValidationError(
                    _("Ya existen incidencias activas generadas para este retroactivo.")
                )

            lines = rec.line_ids.filtered(
                lambda l: l.include and abs(l.difference) > 0.005
            )
            if not lines:
                raise ValidationError(_("No hay diferencias válidas para generar."))

            for line in lines:
                Incident.create({
                    "name": "Retroactivo %s - %s" % (
                        line.concept_name,
                        line.origin_period,
                    ),
                    "employee_id": rec.employee_id.id,
                    "contract_id": rec.contract_id.id,
                    "date": rec.target_date,
                    "incident_type": "retroactive",
                    "quantity": 1.0,
                    "rate": line.difference,
                    "amount": line.difference,
                    "description": (
                        "%s\nPeríodo origen: %s\nRegla origen: %s\n"
                        "Tratamiento: %s\n"
                        "Las cargas sociales, renta, aguinaldo, vacaciones y demás "
                        "efectos legales se calculan mediante el motor principal de "
                        "Nómina Costa Rica y su parametrización vigente."
                        % (
                            rec.reason,
                            line.origin_period,
                            line.salary_rule_code or "-",
                            dict(line._fields["policy"].selection).get(line.policy),
                        )
                    ),
                    "state": "approved",
                    "retroactive_adjustment_id": rec.id,
                    "retroactive_origin_period": line.origin_period,
                })

            rec.state = "generated"

        return True

    @api.onchange("external_report_required")
    def _onchange_external_report_required(self):
        self.external_report_state = (
            "pending" if self.external_report_required else "not_required"
        )

    def action_mark_external_reported(self):
        for rec in self:
            if not rec.external_report_required:
                rec.external_report_state = "not_required"
                continue
            rec.write({
                "external_report_state": "reported",
                "external_reported_by_id": self.env.user.id,
                "external_reported_at": fields.Datetime.now(),
            })
        return True

    def action_mark_external_not_required(self):
        self.write({
            "external_report_required": False,
            "external_report_state": "not_required",
        })
        return True


class CrPayrollRetroactiveAdjustmentLine(models.Model):
    _name = "cr.payroll.retroactive.adjustment.line"
    _description = "Línea de ajuste retroactivo CR"
    _order = "origin_date_from, id"

    adjustment_id = fields.Many2one(
        "cr.payroll.retroactive.adjustment",
        string="Ajuste retroactivo",
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(
        related="adjustment_id.currency_id",
        string="Moneda",
    )
    payslip_id = fields.Many2one(
        "hr.payslip",
        string="Recibo original",
        required=True,
        readonly=True,
    )
    origin_date_from = fields.Date(string="Desde", readonly=True)
    origin_date_to = fields.Date(string="Hasta", readonly=True)
    origin_period = fields.Char(
        string="Período origen",
        compute="_compute_origin_period",
        store=True,
    )
    salary_rule_id = fields.Many2one(
        "hr.salary.rule",
        string="Regla salarial origen",
        readonly=True,
    )
    salary_rule_code = fields.Char(string="Código regla", readonly=True)
    concept_name = fields.Char(string="Concepto", readonly=True)
    policy = fields.Selection([
        ("exclude", "Excluir"),
        ("proportional_wage", "Proporcional al salario"),
        ("fixed", "Mantener original"),
    ], string="Tratamiento", readonly=True)
    original_amount = fields.Monetary(
        string="Importe original",
        currency_field="currency_id",
        readonly=True,
    )
    recalculated_amount = fields.Monetary(
        string="Importe recalculado",
        currency_field="currency_id",
    )
    difference = fields.Monetary(
        string="Diferencia",
        currency_field="currency_id",
        compute="_compute_difference",
        store=True,
    )
    include = fields.Boolean(string="Incluir", default=True)
    notes = fields.Char(string="Observaciones")

    @api.depends("origin_date_from", "origin_date_to")
    def _compute_origin_period(self):
        for line in self:
            if line.origin_date_from and line.origin_date_to:
                line.origin_period = "%s a %s" % (
                    line.origin_date_from,
                    line.origin_date_to,
                )
            else:
                line.origin_period = ""

    @api.depends("original_amount", "recalculated_amount")
    def _compute_difference(self):
        for line in self:
            line.difference = (
                line.recalculated_amount - line.original_amount
            )

    def write(self, vals):
        if any(
            line.adjustment_id.state in ("approved", "generated")
            for line in self
        ):
            raise ValidationError(
                _("No puede modificar líneas de un retroactivo aprobado o generado.")
            )
        return super().write(vals)

    def unlink(self):
        if any(
            line.adjustment_id.state in ("approved", "generated")
            for line in self
        ):
            raise ValidationError(
                _("No puede eliminar líneas de un retroactivo aprobado o generado.")
            )
        return super().unlink()
