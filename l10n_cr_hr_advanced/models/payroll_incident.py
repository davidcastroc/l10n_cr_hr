# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CrPayrollIncident(models.Model):
    _inherit = "cr.payroll.incident"

    incident_type = fields.Selection(
        selection_add=[
            ("productivity", "Productividad"),
            ("availability", "Disponibilidad / guardia"),
            ("salary_difference", "Diferencia salarial"),
            ("late_leave_adjustment", "Ajuste por incapacidad o ausencia tardía"),
        ],
        ondelete={
            "productivity": "cascade",
            "availability": "cascade",
            "salary_difference": "cascade",
            "late_leave_adjustment": "cascade",
        },
    )

    retroactive_adjustment_id = fields.Many2one(
        "cr.payroll.retroactive.adjustment",
        string="Ajuste retroactivo origen",
        index=True,
        copy=False,
        ondelete="set null",
    )
    retroactive_origin_period = fields.Char(
        string="Período origen del retroactivo",
        copy=False,
    )
    late_leave_event_id = fields.Many2one(
        "cr.payroll.late.leave.event",
        string="Evento tardío origen",
        index=True,
        copy=False,
        ondelete="set null",
    )

    @api.constrains("quantity", "rate", "amount", "incident_type")
    def _check_values(self):
        signed_types = {
            "retroactive",
            "salary_difference",
            "aguinaldo_adjustment",
            "late_leave_adjustment",
        }
        for rec in self:
            if rec.quantity < 0:
                raise ValidationError(_("La cantidad no puede ser negativa."))
            if rec.rate < 0 and rec.incident_type not in signed_types:
                raise ValidationError(
                    _("La tarifa no puede ser negativa para este tipo de incidencia.")
                )
            if rec.amount < 0 and rec.incident_type not in signed_types:
                raise ValidationError(
                    _("Este tipo de incidencia no admite importes negativos.")
                )
