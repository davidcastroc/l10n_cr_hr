# -*- coding: utf-8 -*-
from odoo import _, fields, models


class CrPayrollValidationWizard(models.TransientModel):
    _name = "cr.payroll.validation.wizard"
    _description = "Validación previa de nómina Costa Rica"

    payslip_run_id = fields.Many2one("hr.payslip.run", string="Lote")
    result = fields.Text(string="Resultado", readonly=True)

    def action_validate(self):
        self.ensure_one()
        slips = self.payslip_run_id.slip_ids if self.payslip_run_id else self.env["hr.payslip"].browse(self.env.context.get("active_ids", []))
        lines = []
        for slip in slips:
            if slip.cr_validation_message:
                lines.append("%s: %s" % (slip.employee_id.name, slip.cr_validation_message.replace("\n", "; ")))
        self.result = "\n".join(lines) if lines else "No se encontraron bloqueos en los recibos seleccionados."
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "new"}
