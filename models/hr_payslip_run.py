# -*- coding: utf-8 -*-
from odoo import api, fields, models


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
