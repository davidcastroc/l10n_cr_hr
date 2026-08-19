# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CrPayrollHourRecovery(models.Model):
    _name = "cr.payroll.hour.recovery"
    _description = "Reposición de horas Costa Rica"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "deadline_date desc, id desc"

    name = fields.Char(string="Referencia", required=True, default="Nueva reposición", tracking=True)
    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True, index=True, tracking=True)
    contract_id = fields.Many2one("hr.contract", string="Contrato", required=True, domain="[('employee_id','=',employee_id)]", tracking=True)
    company_id = fields.Many2one(related="employee_id.company_id", string="Compañía", store=True, readonly=True)
    origin_date = fields.Date(string="Fecha de la ausencia o tardía", required=True, tracking=True)
    origin_type = fields.Selection([
        ("late_arrival", "Llegada tardía"),
        ("late_lunch", "Regreso tardío de almuerzo"),
        ("early_departure", "Salida anticipada"),
        ("personal_permission", "Permiso personal"),
        ("other", "Otro"),
    ], string="Tipo de tiempo pendiente", required=True, default="late_arrival", tracking=True)
    hours_to_recover = fields.Float(string="Horas autorizadas para reponer", required=True, tracking=True)
    valid_from = fields.Date(string="Puede reponer desde", required=True, tracking=True)
    deadline_date = fields.Date(string="Fecha límite para reponer", required=True, tracking=True)
    reason = fields.Text(string="Motivo / justificación", required=True)
    attachment_ids = fields.Many2many("ir.attachment", string="Documentos / evidencia")
    plan_line_ids = fields.One2many("cr.payroll.hour.recovery.line", "recovery_id", string="Días y horarios de reposición")
    planned_hours = fields.Float(string="Horas planificadas", compute="_compute_hours")
    recovered_hours = fields.Float(string="Horas efectivamente repuestas", compute="_compute_hours")
    remaining_hours = fields.Float(string="Saldo pendiente por reponer", compute="_compute_hours")
    excess_hours = fields.Float(string="Horas excedentes potencialmente extra", compute="_compute_hours")
    state = fields.Selection([
        ("draft", "Borrador"),
        ("to_approve", "Por aprobar"),
        ("approved", "Aprobada"),
        ("partial", "Parcialmente repuesta"),
        ("done", "Repuesta"),
        ("expired", "Vencida"),
        ("cancel", "Cancelada"),
    ], string="Estado", default="draft", required=True, tracking=True)
    requested_by_id = fields.Many2one("res.users", string="Registrado por", default=lambda self: self.env.user, readonly=True)
    approved_by_id = fields.Many2one("res.users", string="Aprobado por", readonly=True, copy=False)
    approved_at = fields.Datetime(string="Fecha de aprobación", readonly=True, copy=False)
    closed_at = fields.Datetime(string="Fecha de cierre", readonly=True, copy=False)
    payroll_incident_id = fields.Many2one("cr.payroll.incident", string="Incidencia de nómina por saldo vencido", readonly=True, copy=False)
    notes = fields.Text(string="Observaciones internas")

    @api.depends("hours_to_recover", "plan_line_ids.planned_hours", "plan_line_ids.actual_hours")
    def _compute_hours(self):
        for rec in self:
            planned = sum(rec.plan_line_ids.mapped("planned_hours"))
            actual = sum(rec.plan_line_ids.mapped("actual_hours"))
            effective = min(actual, rec.hours_to_recover or 0.0)
            rec.planned_hours = planned
            rec.recovered_hours = effective
            rec.remaining_hours = max((rec.hours_to_recover or 0.0) - effective, 0.0)
            rec.excess_hours = max(actual - (rec.hours_to_recover or 0.0), 0.0)

    @api.constrains("employee_id", "contract_id")
    def _check_contract_employee(self):
        for rec in self:
            if rec.contract_id and rec.contract_id.employee_id != rec.employee_id:
                raise ValidationError(_("El contrato seleccionado no pertenece al empleado."))

    @api.constrains("hours_to_recover", "origin_date", "valid_from", "deadline_date")
    def _check_values(self):
        for rec in self:
            if rec.hours_to_recover <= 0:
                raise ValidationError(_("Las horas a reponer deben ser mayores que cero."))
            if rec.deadline_date < rec.valid_from:
                raise ValidationError(_("La fecha límite no puede ser anterior a la fecha inicial de reposición."))
            if rec.valid_from < rec.origin_date:
                raise ValidationError(_("La reposición no puede iniciar antes de la ausencia o tardía que la originó."))

    def action_submit(self):
        for rec in self:
            if not rec.plan_line_ids:
                raise ValidationError(_("Debe indicar al menos un día y horario en que se realizará la reposición."))
            if rec.planned_hours + 0.00001 < rec.hours_to_recover:
                raise ValidationError(_("Las horas planificadas no cubren el total autorizado para reponer."))
            rec.state = "to_approve"
        return True

    def action_approve(self):
        for rec in self:
            if rec.state != "to_approve":
                raise ValidationError(_("La reposición debe estar por aprobar."))
            rec.write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_at": fields.Datetime.now(),
            })
        return True

    def action_reconcile(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state not in ("approved", "partial", "expired"):
                continue
            # Fuerza la lectura de las asistencias reales de cada horario aprobado.
            rec.plan_line_ids.invalidate_recordset(["actual_hours"])
            remaining = rec.remaining_hours
            if remaining <= 0.00001:
                rec.write({"state": "done", "closed_at": fields.Datetime.now()})
            elif today > rec.deadline_date:
                rec.state = "expired"
                rec._create_expired_incident()
            elif rec.recovered_hours > 0:
                rec.state = "partial"
            else:
                rec.state = "approved"
        return True

    def _create_expired_incident(self):
        self.ensure_one()
        if self.remaining_hours <= 0.00001 or self.payroll_incident_id:
            return self.payroll_incident_id
        incident = self.env["cr.payroll.incident"].sudo().create({
            "name": "Horas no repuestas - %s" % self.employee_id.name,
            "employee_id": self.employee_id.id,
            "contract_id": self.contract_id.id,
            "date": fields.Date.context_today(self),
            "incident_type": "unpaid_hours",
            "quantity": self.remaining_hours,
            "rate": 1.0,
            "amount": self.remaining_hours,
            "description": "Reposición vencida. Origen: %s. Fecha límite: %s. Motivo: %s" % (
                self.origin_date, self.deadline_date, self.reason or "-"
            ),
            "state": "approved",
            "hour_recovery_id": self.id,
            "attendance_origin_period": "%s a %s" % (self.valid_from, self.deadline_date),
        })
        self.payroll_incident_id = incident.id
        return incident

    def action_reschedule(self):
        for rec in self:
            if rec.state not in ("approved", "partial"):
                raise ValidationError(_("Solo puede reprogramar una reposición aprobada o parcialmente repuesta."))
            if rec.remaining_hours <= 0.00001:
                raise ValidationError(_("La reposición ya está completa y no requiere reprogramación."))
            rec.write({
                "state": "draft",
                "approved_by_id": False,
                "approved_at": False,
            })
        return True

    def action_cancel(self):
        for rec in self:
            if rec.payroll_incident_id and rec.payroll_incident_id.state not in ("cancel", "rejected"):
                raise ValidationError(_("No puede cancelar la reposición porque ya existe una incidencia activa de nómina."))
            rec.state = "cancel"
        return True

    @api.model
    def _cron_reconcile_hour_recoveries(self):
        records = self.search([("state", "in", ["approved", "partial", "expired"])])
        records.action_reconcile()


class CrPayrollHourRecoveryLine(models.Model):
    _name = "cr.payroll.hour.recovery.line"
    _description = "Horario planificado de reposición de horas"
    _order = "date_start, id"

    recovery_id = fields.Many2one("cr.payroll.hour.recovery", string="Reposición", required=True, ondelete="cascade")
    employee_id = fields.Many2one(related="recovery_id.employee_id", string="Empleado", store=True, readonly=True)
    date_start = fields.Datetime(string="Inicio de reposición", required=True)
    date_stop = fields.Datetime(string="Fin de reposición", required=True)
    planned_hours = fields.Float(string="Horas planificadas", compute="_compute_planned_hours", store=True)
    actual_hours = fields.Float(string="Horas comprobadas por asistencia", compute="_compute_actual_hours")
    attendance_ids = fields.Many2many("hr.attendance", string="Marcaciones utilizadas", compute="_compute_actual_hours")
    notes = fields.Char(string="Observaciones")

    @api.depends("date_start", "date_stop")
    def _compute_planned_hours(self):
        for line in self:
            if line.date_start and line.date_stop and line.date_stop > line.date_start:
                line.planned_hours = (line.date_stop - line.date_start).total_seconds() / 3600.0
            else:
                line.planned_hours = 0.0

    @api.depends("date_start", "date_stop", "employee_id")
    def _compute_actual_hours(self):
        Attendance = self.env["hr.attendance"].sudo()
        for line in self:
            total = 0.0
            used = Attendance.browse()
            if line.employee_id and line.date_start and line.date_stop:
                attendances = Attendance.search([
                    ("employee_id", "=", line.employee_id.id),
                    ("check_in", "<", line.date_stop),
                    ("check_out", ">", line.date_start),
                ])
                for att in attendances.filtered("check_out"):
                    start = max(att.check_in, line.date_start)
                    stop = min(att.check_out, line.date_stop)
                    if stop > start:
                        total += (stop - start).total_seconds() / 3600.0
                        used |= att
            line.actual_hours = total
            line.attendance_ids = used

    def write(self, vals):
        protected = {"date_start", "date_stop", "recovery_id"}
        if protected.intersection(vals) and any(line.recovery_id.state in ("approved", "partial", "done", "expired") for line in self):
            raise ValidationError(_("No puede modificar un horario ya aprobado. Use Reprogramar para cambiarlo y vuelva a aprobar."))
        return super().write(vals)

    def unlink(self):
        if any(line.recovery_id.state in ("approved", "partial", "done", "expired") for line in self):
            raise ValidationError(_("No puede eliminar un horario de reposición ya aprobado."))
        return super().unlink()

    @api.constrains("date_start", "date_stop", "recovery_id")
    def _check_dates(self):
        for line in self:
            if line.date_start and line.date_stop and line.date_stop <= line.date_start:
                raise ValidationError(_("El fin de la reposición debe ser posterior al inicio."))
            if not line.recovery_id or not line.date_start or not line.date_stop:
                continue
            start_date = fields.Datetime.context_timestamp(line, line.date_start).date()
            stop_date = fields.Datetime.context_timestamp(line, line.date_stop).date()
            if start_date < line.recovery_id.valid_from or stop_date > line.recovery_id.deadline_date:
                raise ValidationError(_("El horario debe estar dentro del rango autorizado para la reposición."))
            overlap = self.search_count([
                ("id", "!=", line.id),
                ("employee_id", "=", line.employee_id.id),
                ("recovery_id.state", "in", ["to_approve", "approved", "partial"]),
                ("date_start", "<", line.date_stop),
                ("date_stop", ">", line.date_start),
            ])
            if overlap:
                raise ValidationError(_("El empleado ya tiene otro horario de reposición que se cruza con este intervalo."))
