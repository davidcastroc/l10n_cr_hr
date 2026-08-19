# -*- coding: utf-8 -*-
from odoo import fields, models


class ResourceCalendarLeaves(models.Model):
    _inherit = "resource.calendar.leaves"

    cr_is_public_holiday = fields.Boolean(
        string="Feriado legal de Costa Rica",
        default=False,
        help="Identifica el registro como feriado legal costarricense generado por la localización.",
    )
    cr_mandatory_pay = fields.Boolean(
        string="Pago obligatorio",
        help="Indica si el feriado es de pago obligatorio según la normativa costarricense.",
    )
    cr_holiday_type = fields.Selection(
        [("fixed", "Fecha fija"), ("movable", "Fecha móvil")],
        string="Tipo de feriado CR",
        default="fixed",
    )
    cr_legal_source = fields.Char(string="Fuente legal CR")
