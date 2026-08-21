# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CrAttendanceCorrection(models.Model):
    _name = "cr.attendance.correction"
    _description = "Corrección auditada de marcación"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "request_date desc, id desc"

    name = fields.Char(
        string="Referencia",
        required=True,
        default="Corrección de marcación",
        tracking=True,
    )
    attendance_id = fields.Many2one(
        "hr.attendance",
        string="Marcación original",
        required=True,
        tracking=True,
    )
    employee_id = fields.Many2one(
        related="attendance_id.employee_id",
        string="Empleado",
        store=True,
        readonly=True,
    )
    original_check_in = fields.Datetime(
        string="Entrada original",
        readonly=True,
        copy=False,
    )
    original_check_out = fields.Datetime(
        string="Salida original",
        readonly=True,
        copy=False,
    )
    proposed_check_in = fields.Datetime(
        string="Entrada corregida",
        required=True,
    )
    proposed_check_out = fields.Datetime(string="Salida corregida")

    reason = fields.Text(string="Motivo de corrección", required=True)
    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="Evidencia",
    )
    request_date = fields.Datetime(
        string="Fecha de solicitud",
        default=fields.Datetime.now,
        readonly=True,
    )
    state = fields.Selection([
        ("draft", "Borrador"),
        ("to_approve", "Por aprobar"),
        ("approved", "Aprobado"),
        ("rejected", "Rechazado"),
        ("cancel", "Cancelado"),
    ], string="Estado", default="draft", tracking=True)

    requested_by_id = fields.Many2one(
        "res.users",
        string="Solicitado por",
        default=lambda self: self.env.user,
        readonly=True,
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
    )

    def _is_system_administrator(self):
        self.ensure_one()
        return self.env.user.has_group("base.group_system")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.attendance_id:
                rec.write({
                    "original_check_in": rec.attendance_id.check_in,
                    "original_check_out": rec.attendance_id.check_out,
                    "proposed_check_in": (
                        rec.proposed_check_in
                        or rec.attendance_id.check_in
                    ),
                    "proposed_check_out": (
                        rec.proposed_check_out
                        or rec.attendance_id.check_out
                    ),
                })
        return records

    @api.onchange("attendance_id")
    def _onchange_attendance_id(self):
        if self.attendance_id:
            self.original_check_in = self.attendance_id.check_in
            self.original_check_out = self.attendance_id.check_out
            self.proposed_check_in = self.attendance_id.check_in
            self.proposed_check_out = self.attendance_id.check_out

    @api.constrains("proposed_check_in", "proposed_check_out")
    def _check_proposed_dates(self):
        for rec in self:
            if (
                rec.proposed_check_in
                and rec.proposed_check_out
                and rec.proposed_check_out <= rec.proposed_check_in
            ):
                raise ValidationError(_(
                    "La salida corregida debe ser posterior a la entrada corregida."
                ))

    def action_submit(self):
        for rec in self:
            if not rec.reason:
                raise ValidationError(
                    _("Debe indicar el motivo de la corrección.")
                )
            if not rec.attachment_ids:
                raise ValidationError(
                    _("Debe adjuntar evidencia para solicitar la corrección.")
                )
            rec.state = "to_approve"
        return True

    def action_approve(self):
        for rec in self:
            if rec.state != "to_approve":
                raise ValidationError(
                    _("La corrección no está pendiente de aprobación.")
                )

            is_admin = rec._is_system_administrator()
            if rec.requested_by_id == self.env.user and not is_admin:
                raise ValidationError(_(
                    "Por control interno, quien solicita la corrección no puede aprobarla. "
                    "Un Administrador del sistema sí puede realizar ambas acciones."
                ))

            rec.attendance_id.sudo().write({
                "check_in": rec.proposed_check_in,
                "check_out": rec.proposed_check_out,
            })
            rec.write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_at": fields.Datetime.now(),
                "administrative_self_approval": bool(
                    is_admin and rec.requested_by_id == self.env.user
                ),
            })
            rec.message_post(body=_(
                "Marcación corregida. Entrada original: %(in_old)s. "
                "Salida original: %(out_old)s. Entrada nueva: %(in_new)s. "
                "Salida nueva: %(out_new)s.",
                in_old=rec.original_check_in,
                out_old=rec.original_check_out,
                in_new=rec.proposed_check_in,
                out_new=rec.proposed_check_out,
            ))

        return True

    def action_reject(self):
        self.filtered(
            lambda r: r.state == "to_approve"
        ).write({"state": "rejected"})
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == "approved":
                raise ValidationError(_(
                    "Una corrección aprobada no puede cancelarse porque ya modificó la marcación."
                ))
            rec.state = "cancel"
        return True

    def write(self, vals):
        protected = {
            "attendance_id",
            "proposed_check_in",
            "proposed_check_out",
            "reason",
            "attachment_ids",
        }
        if protected.intersection(vals) and any(
            rec.state == "approved" for rec in self
        ):
            raise ValidationError(
                _("No se puede modificar una corrección ya aprobada.")
            )
        return super().write(vals)

    def unlink(self):
        if any(rec.state == "approved" for rec in self):
            raise ValidationError(
                _("No se puede eliminar una corrección ya aprobada.")
            )
        return super().unlink()
