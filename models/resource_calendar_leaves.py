# -*- coding: utf-8 -*-
from odoo import fields, models


class ResourceCalendarLeaves(models.Model):
    _inherit = "resource.calendar.leaves"

    cr_is_public_holiday = fields.Boolean(string="Feriado Costa Rica", default=False, index=True)
    cr_mandatory_pay = fields.Boolean(string="Pago obligatorio", default=True)
    cr_holiday_type = fields.Selection([
        ("fixed", "Fijo"),
        ("movable", "Móvil"),
    ], string="Tipo de feriado", default="fixed")
    cr_legal_source = fields.Char(string="Fuente legal")
