# -*- coding: utf-8 -*-
from datetime import date, datetime, time, timedelta

from odoo import _, fields, models


class CrGenerateHolidaysWizard(models.TransientModel):
    _name = "cr.generate.holidays.wizard"
    _description = "Generar feriados de Costa Rica en Ausencias"

    year = fields.Integer(
        string="Año",
        required=True,
        default=lambda self: fields.Date.today().year,
    )

    @staticmethod
    def _easter_sunday(year):
        a = year % 19
        b, c = divmod(year, 100)
        d, e = divmod(b, 4)
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i, k = divmod(c, 4)
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    def _holiday_values(self):
        easter = self._easter_sunday(self.year)
        fixed = [
            (1, 1, "Año Nuevo", True),
            (4, 11, "Día de Juan Santamaría", True),
            (5, 1, "Día Internacional del Trabajo", True),
            (7, 25, "Anexión del Partido de Nicoya", True),
            (8, 2, "Virgen de los Ángeles", False),
            (8, 15, "Día de la Madre", True),
            (8, 31, "Día de la Persona Negra y la Cultura Afrocostarricense", False),
            (9, 15, "Independencia de Costa Rica", True),
            (12, 1, "Abolición del Ejército", False),
            (12, 25, "Navidad", True),
        ]
        values = [(date(self.year, m, d), name, mandatory, "fixed") for m, d, name, mandatory in fixed]
        values += [
            (easter - timedelta(days=3), "Jueves Santo", True, "movable"),
            (easter - timedelta(days=2), "Viernes Santo", True, "movable"),
        ]
        return values

    def action_generate(self):
        self.ensure_one()
        Holiday = self.env["resource.calendar.leaves"].sudo()
        created = skipped = 0
        for holiday_date, name, mandatory, holiday_type in self._holiday_values():
            start = datetime.combine(holiday_date, time.min)
            end = start + timedelta(days=1)
            # Odoo impide cualquier traslape, no solo duplicados creados por este módulo.
            overlap_domain = [
                ("resource_id", "=", False),
                ("date_from", "<", fields.Datetime.to_string(end)),
                ("date_to", ">", fields.Datetime.to_string(start)),
                ("company_id", "in", [False, self.env.company.id]),
            ]
            if Holiday.search_count(overlap_domain):
                skipped += 1
                continue
            Holiday.create({
                "name": "CR - %s" % name,
                "date_from": fields.Datetime.to_string(start),
                "date_to": fields.Datetime.to_string(end),
                "company_id": self.env.company.id,
                "calendar_id": False,
                "resource_id": False,
                "cr_is_public_holiday": True,
                "cr_mandatory_pay": mandatory,
                "cr_holiday_type": holiday_type,
                "cr_legal_source": "Código de Trabajo / MTSS",
            })
            created += 1
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Feriados de Costa Rica"),
                "message": _("Creados: %(created)s. Existentes omitidos: %(skipped)s.", created=created, skipped=skipped),
                "type": "success",
                "sticky": False,
            },
        }
