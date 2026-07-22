# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    cr_process_type = fields.Selection(
        [
            ("ordinary", "Nómina ordinaria"),
            ("aguinaldo", "Aguinaldo"),
            ("extraordinary", "Pago extraordinario"),
            ("settlement", "Liquidación laboral"),
        ],
        string="Tipo de proceso Costa Rica",
        default="ordinary",
        required=True,
    )
    cr_is_aguinaldo = fields.Boolean(
        string="Es aguinaldo",
        compute="_compute_cr_flags",
        store=True,
    )

    @api.depends("cr_process_type")
    def _compute_cr_flags(self):
        for run in self:
            run.cr_is_aguinaldo = run.cr_process_type == "aguinaldo"


    def action_cr_validate_payroll(self):
        self.ensure_one()
        issues = []
        for slip in self.slip_ids:
            if slip.cr_validation_message:
                issues.append("%s: %s" % (
                    slip.employee_id.name,
                    slip.cr_validation_message.replace("\n", "; "),
                ))
        if issues:
            raise UserError(
                _("La nómina tiene bloqueos:\n%s") % "\n".join(issues)
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Validación de nómina"),
                "message": _("Todos los recibos del lote pasaron las validaciones."),
                "type": "success",
                "sticky": False,
            },
        }
