# -*- coding: utf-8 -*-
from datetime import date, datetime, time, timedelta
from odoo import _, fields, models
from odoo.exceptions import UserError


class CrGenerateHolidaysWizard(models.TransientModel):
    _name = "cr.generate.holidays.wizard"
    _description = "Generar feriados de Costa Rica"

    year = fields.Integer(string="Año", required=True, default=lambda self: fields.Date.today().year)

    def _easter_sunday(self, year):
        a = year % 19; b = year // 100; c = year % 100; d = b // 4; e = b % 4
        f = (b + 8) // 25; g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30
        i = c // 4; k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451; month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    def _holidays(self):
        easter = self._easter_sunday(self.year)
        return [
            (date(self.year, 1, 1), "Año Nuevo", True, "fixed"),
            (easter - timedelta(days=3), "Jueves Santo", True, "movable"),
            (easter - timedelta(days=2), "Viernes Santo", True, "movable"),
            (date(self.year, 4, 11), "Día de Juan Santamaría", True, "fixed"),
            (date(self.year, 5, 1), "Día Internacional del Trabajo", True, "fixed"),
            (date(self.year, 7, 25), "Anexión del Partido de Nicoya", True, "fixed"),
            (date(self.year, 8, 2), "Virgen de los Ángeles", False, "fixed"),
            (date(self.year, 8, 15), "Día de la Madre", True, "fixed"),
            (date(self.year, 8, 31), "Día de la Persona Negra y la Cultura Afrocostarricense", False, "fixed"),
            (date(self.year, 9, 15), "Día de la Independencia", True, "fixed"),
            (date(self.year, 12, 1), "Abolición del Ejército", False, "fixed"),
            (date(self.year, 12, 25), "Navidad", True, "fixed"),
        ]

    def action_generate(self):
        self.ensure_one()
        if self.year < 2000 or self.year > 2100:
            raise UserError(_("El año indicado no es válido."))
        Holiday = self.env["resource.calendar.leaves"].sudo()
        created = skipped = 0
        for holiday_date, name, mandatory, holiday_type in self._holidays():
            start = datetime.combine(holiday_date, time.min)
            end = datetime.combine(holiday_date, time.max)
            exists = Holiday.search_count([
                ("resource_id", "=", False), ("date_from", "<=", fields.Datetime.to_string(end)),
                ("date_to", ">=", fields.Datetime.to_string(start)),
                "|", ("company_id", "=", False), ("company_id", "=", self.env.company.id),
            ])
            if exists:
                skipped += 1
                continue
            Holiday.create({
                "name": "CR - %s" % name, "date_from": start, "date_to": end,
                "company_id": self.env.company.id, "calendar_id": False, "resource_id": False,
                "cr_is_public_holiday": True, "cr_mandatory_pay": mandatory,
                "cr_holiday_type": holiday_type, "cr_legal_source": "Código de Trabajo, artículo 148",
            })
            created += 1
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"title": _("Feriados de Costa Rica"), "message": _("Creados: %(created)s. Omitidos: %(skipped)s.", created=created, skipped=skipped), "type": "success", "sticky": False, "next": {"type": "ir.actions.act_window_close"}}}
