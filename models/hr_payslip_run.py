# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    cr_process_type = fields.Selection([
        ("regular", "Nómina ordinaria"),
        ("extraordinary", "Pago extraordinario"),
        ("aguinaldo", "Aguinaldo"),
        ("settlement", "Liquidación laboral"),
    ], string="Tipo de proceso", default="regular", required=True)
    cr_is_aguinaldo = fields.Boolean(compute="_compute_cr_is_aguinaldo")

    def _compute_cr_is_aguinaldo(self):
        for run in self:
            run.cr_is_aguinaldo = run.cr_process_type == "aguinaldo"
