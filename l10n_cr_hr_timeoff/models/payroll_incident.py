# -*- coding: utf-8 -*-
from odoo import fields, models


class CrPayrollIncident(models.Model):
    _inherit = "cr.payroll.incident"

    incident_type = fields.Selection(
        selection_add=[
            ("vacation_pay", "Pago de vacaciones"),
            ("ccss_disability", "Pago incapacidad CCSS"),
            ("ins_disability", "Pago incapacidad INS"),
            ("maternity", "Pago maternidad"),
            ("paternity", "Pago paternidad"),
        ],
        ondelete={
            "vacation_pay": "cascade",
            "ccss_disability": "cascade",
            "ins_disability": "cascade",
            "maternity": "cascade",
            "paternity": "cascade",
        },
    )
