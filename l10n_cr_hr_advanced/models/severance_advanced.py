# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


REFERENCE_COMPONENTS = [
    ("pending_salary", "Salario pendiente"),
    ("pending_commissions", "Comisiones"),
    ("pending_overtime", "Horas extra"),
    ("vacation_amount", "Vacaciones"),
    ("aguinaldo_amount", "Aguinaldo proporcional"),
    ("notice_amount", "Preaviso"),
    ("severance_amount", "Cesantía"),
    ("other_income", "Otros ingresos"),
    ("deductions", "Deducciones"),
]


class CrPayrollTermination(models.Model):
    _inherit = "cr.payroll.termination"

    reference_locked = fields.Boolean(
        string="Referencia legal congelada",
        readonly=True,
        copy=False,
    )
    reference_locked_by_id = fields.Many2one(
        "res.users",
        string="Referencia congelada por",
        readonly=True,
        copy=False,
    )
    reference_locked_at = fields.Datetime(
        string="Fecha de congelamiento",
        readonly=True,
        copy=False,
    )

    agreement_line_ids = fields.One2many(
        "cr.payroll.termination.agreement.line",
        "termination_id",
        string="Acuerdo negociado",
    )
    agreement_attachment_ids = fields.Many2many(
        "ir.attachment",
        "cr_term_agreement_attachment_rel",
        "termination_id",
        "attachment_id",
        string="Acuerdo firmado",
    )
    agreement_state = fields.Selection([
        ("none", "Sin acuerdo"),
        ("draft", "Borrador"),
        ("approved", "Aprobado"),
        ("reversed", "Revertido"),
    ], default="none", string="Estado acuerdo", tracking=True)

    agreement_operator_id = fields.Many2one(
        "res.users",
        string="Preparado por",
        readonly=True,
        copy=False,
    )
    administrative_self_approval = fields.Boolean(
        string="Autoaprobación administrativa",
        readonly=True,
        copy=False,
        help="Se activa cuando un Administrador del sistema prepara y aprueba el mismo acuerdo.",
    )
    agreement_approved_by_id = fields.Many2one(
        "res.users",
        string="Acuerdo aprobado por",
        readonly=True,
        copy=False,
    )
    agreement_approved_at = fields.Datetime(
        string="Fecha de aprobación del acuerdo",
        readonly=True,
        copy=False,
    )

    agreement_total = fields.Monetary(
        string="Total acordado",
        compute="_compute_agreement_totals",
        currency_field="currency_id",
    )
    agreement_difference = fields.Monetary(
        string="Diferencia contra referencia legal",
        compute="_compute_agreement_totals",
        currency_field="currency_id",
    )

    loan_balance_before = fields.Monetary(
        string="Saldo préstamo antes",
        currency_field="currency_id",
    )
    loan_deduction_agreed = fields.Monetary(
        string="Préstamo a deducir",
        currency_field="currency_id",
    )
    loan_residual_receivable = fields.Monetary(
        compute="_compute_agreement_totals",
        string="Saldo residual CxC",
        currency_field="currency_id",
    )

    receivable_journal_id = fields.Many2one(
        "account.journal",
        string="Diario para cuenta por cobrar",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    receivable_account_id = fields.Many2one(
        "account.account",
        string="Cuenta por cobrar al colaborador",
        domain="[('company_ids', 'in', company_id)]",
    )
    receivable_counterpart_account_id = fields.Many2one(
        "account.account",
        string="Cuenta contrapartida de liquidación",
        domain="[('company_ids', 'in', company_id)]",
    )
    residual_receivable_move_id = fields.Many2one(
        "account.move",
        string="Asiento de cuenta por cobrar",
        readonly=True,
        copy=False,
    )

    pending_overtime_incident_ids = fields.Many2many(
        "cr.payroll.incident",
        string="Horas extra pendientes de aprobación",
        compute="_compute_pending_overtime_incidents",
    )

    @api.depends(
        "agreement_line_ids.agreed_amount",
        "agreement_line_ids.reference_amount",
        "loan_balance_before",
        "loan_deduction_agreed",
    )
    def _compute_agreement_totals(self):
        for rec in self:
            rec.agreement_total = sum(rec.agreement_line_ids.mapped("agreed_amount"))
            rec.agreement_difference = sum(rec.agreement_line_ids.mapped("difference"))
            rec.loan_residual_receivable = max(
                (rec.loan_balance_before or 0.0) - (rec.loan_deduction_agreed or 0.0),
                0.0,
            )

    def _compute_pending_overtime_incidents(self):
        Incident = self.env["cr.payroll.incident"].sudo()
        for rec in self:
            pending = Incident.search([
                ("employee_id", "=", rec.employee_id.id),
                ("state", "not in", ["approved", "cancel", "rejected"]),
            ])
            pending = pending.filtered(
                lambda i: (
                    "overtime" in (i.incident_type or "").lower()
                    or "extra" in (i.incident_type or "").lower()
                    or "hora extra" in (i.name or "").lower()
                )
            )
            rec.pending_overtime_incident_ids = pending

    def _check_no_pending_overtime(self):
        for rec in self:
            if rec.pending_overtime_incident_ids:
                raise ValidationError(_(
                    "No puede congelar ni aprobar la liquidación mientras existan "
                    "horas extra pendientes de aprobación para el colaborador."
                ))

    def _is_system_administrator(self):
        self.ensure_one()
        return self.env.user.has_group("base.group_system")

    def action_freeze_legal_reference(self):
        Line = self.env["cr.payroll.termination.agreement.line"].sudo()

        for rec in self:
            rec._check_no_pending_overtime()

            if rec.reference_locked:
                continue

            rec.agreement_line_ids.unlink()

            for field_name, label in REFERENCE_COMPONENTS:
                amount = rec[field_name] or 0.0
                signed = -amount if field_name == "deductions" else amount

                Line.create({
                    "termination_id": rec.id,
                    "component": field_name,
                    "name": label,
                    "reference_amount": signed,
                    "agreed_amount": signed,
                })

            rec.write({
                "reference_locked": True,
                "reference_locked_by_id": self.env.user.id,
                "reference_locked_at": fields.Datetime.now(),
                "agreement_state": "draft",
                "agreement_operator_id": self.env.user.id,
            })
        return True

    def action_approve_agreement(self):
        for rec in self:
            rec._check_no_pending_overtime()

            if not rec.reference_locked:
                raise ValidationError(
                    _("Primero debe congelar el cálculo legal de referencia.")
                )

            is_admin = rec._is_system_administrator()
            if rec.agreement_operator_id == self.env.user and not is_admin:
                raise ValidationError(
                    _(
                        "Por control interno, quien prepara el acuerdo no puede aprobarlo. "
                        "Un Administrador del sistema sí puede realizar ambas acciones."
                    )
                )

            if not rec.agreement_attachment_ids:
                raise ValidationError(
                    _("Debe adjuntar el acuerdo firmado antes de aprobarlo.")
                )

            changed = rec.agreement_line_ids.filtered(
                lambda l: abs(l.difference) > 0.005
            )

            for line in changed:
                if not line.reason:
                    raise ValidationError(
                        _("Toda diferencia negociada debe indicar un motivo: %s") % line.name
                    )
                if not line.attachment_ids and not rec.agreement_attachment_ids:
                    raise ValidationError(
                        _("Toda diferencia negociada debe tener respaldo documental: %s") % line.name
                    )

            rec.write({
                "agreement_state": "approved",
                "agreement_approved_by_id": self.env.user.id,
                "agreement_approved_at": fields.Datetime.now(),
                "administrative_self_approval": bool(
                    is_admin and rec.agreement_operator_id == self.env.user
                ),
            })

        return True

    def action_create_residual_receivable(self):
        Move = self.env["account.move"].sudo()

        for rec in self:
            if rec.agreement_state != "approved":
                raise ValidationError(
                    _("El acuerdo debe estar aprobado antes de generar la cuenta por cobrar.")
                )

            if rec.loan_residual_receivable <= 0:
                raise ValidationError(
                    _("No existe saldo residual de préstamo para generar una cuenta por cobrar.")
                )

            if rec.residual_receivable_move_id:
                raise ValidationError(
                    _("Ya existe un asiento de cuenta por cobrar para esta liquidación.")
                )

            if not rec.receivable_journal_id:
                raise ValidationError(_("Debe seleccionar el diario contable."))
            if not rec.receivable_account_id:
                raise ValidationError(_("Debe seleccionar la cuenta por cobrar al colaborador."))
            if not rec.receivable_counterpart_account_id:
                raise ValidationError(_("Debe seleccionar la cuenta contrapartida."))

            partner = rec.employee_id.work_contact_id

            move = Move.create({
                "move_type": "entry",
                "date": fields.Date.context_today(rec),
                "journal_id": rec.receivable_journal_id.id,
                "ref": "CxC liquidación - %s" % rec.employee_id.name,
                "line_ids": [
                    (0, 0, {
                        "name": "Saldo préstamo por cobrar - %s" % rec.employee_id.name,
                        "partner_id": partner.id if partner else False,
                        "account_id": rec.receivable_account_id.id,
                        "debit": rec.loan_residual_receivable,
                        "credit": 0.0,
                    }),
                    (0, 0, {
                        "name": "Contrapartida liquidación - %s" % rec.employee_id.name,
                        "partner_id": partner.id if partner else False,
                        "account_id": rec.receivable_counterpart_account_id.id,
                        "debit": 0.0,
                        "credit": rec.loan_residual_receivable,
                    }),
                ],
            })
            move.action_post()
            rec.residual_receivable_move_id = move.id

        return True

    def action_reverse_agreement(self):
        for rec in self:
            if rec.residual_receivable_move_id and rec.residual_receivable_move_id.state == "posted":
                raise ValidationError(_(
                    "No puede revertir el acuerdo mientras exista un asiento de cuenta por cobrar "
                    "publicado. Revierta primero el asiento contable."
                ))
            rec.write({"agreement_state": "reversed"})
        return True


class CrPayrollTerminationAgreementLine(models.Model):
    _name = "cr.payroll.termination.agreement.line"
    _description = "Diferencia de acuerdo de liquidación CR"
    _order = "id"

    termination_id = fields.Many2one(
        "cr.payroll.termination",
        string="Liquidación",
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(
        related="termination_id.currency_id",
        string="Moneda",
    )
    component = fields.Char(
        string="Código del componente",
        required=True,
        readonly=True,
    )
    name = fields.Char(string="Concepto", required=True, readonly=True)
    reference_amount = fields.Monetary(
        string="Importe legal de referencia",
        currency_field="currency_id",
        readonly=True,
    )
    agreed_amount = fields.Monetary(
        string="Importe acordado",
        currency_field="currency_id",
    )
    difference = fields.Monetary(
        string="Diferencia",
        compute="_compute_difference",
        currency_field="currency_id",
    )
    reason = fields.Text(string="Motivo de diferencia")
    attachment_ids = fields.Many2many("ir.attachment", string="Evidencia")
    approved_by_id = fields.Many2one(
        string="Aprobado por",
        related="termination_id.agreement_approved_by_id",
        readonly=True,
    )

    @api.depends("reference_amount", "agreed_amount")
    def _compute_difference(self):
        for rec in self:
            rec.difference = rec.agreed_amount - rec.reference_amount

    def write(self, vals):
        if any(line.termination_id.agreement_state == "approved" for line in self):
            raise ValidationError(
                _("No se puede modificar un acuerdo aprobado. Debe revertirse formalmente.")
            )
        return super().write(vals)

    def unlink(self):
        if any(line.termination_id.agreement_state == "approved" for line in self):
            raise ValidationError(
                _("No se puede eliminar una línea de un acuerdo aprobado.")
            )
        return super().unlink()
