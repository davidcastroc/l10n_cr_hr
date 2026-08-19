# -*- coding: utf-8 -*-

from datetime import date, datetime, time, timedelta

from odoo import _, fields, models
from odoo.exceptions import ValidationError


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
        """Calcula la fecha del Domingo de Resurrección."""

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
        """Devuelve los feriados legales configurados para Costa Rica."""

        self.ensure_one()

        easter = self._easter_sunday(self.year)

        fixed_holidays = [
            (1, 1, "Año Nuevo", True),
            (4, 11, "Día de Juan Santamaría", True),
            (5, 1, "Día Internacional del Trabajo", True),
            (7, 25, "Anexión del Partido de Nicoya", True),
            (8, 2, "Virgen de los Ángeles", False),
            (8, 15, "Día de la Madre", True),
            (
                8,
                31,
                "Día de la Persona Negra y la Cultura Afrocostarricense",
                False,
            ),
            (9, 15, "Independencia de Costa Rica", True),
            (12, 1, "Abolición del Ejército", False),
            (12, 25, "Navidad", True),
        ]

        holidays = [
            (
                date(self.year, month, day),
                name,
                mandatory,
                "fixed",
            )
            for month, day, name, mandatory in fixed_holidays
        ]

        holidays.extend([
            (
                easter - timedelta(days=3),
                "Jueves Santo",
                True,
                "movable",
            ),
            (
                easter - timedelta(days=2),
                "Viernes Santo",
                True,
                "movable",
            ),
        ])

        return sorted(holidays, key=lambda item: item[0])

    def _prepare_holiday_datetimes(self, holiday_date):
        """Construye un rango del mismo día sin tocar el día siguiente.

        El final se establece a las 23:59:59 para evitar que dos feriados
        consecutivos se consideren traslapados por la validación interna
        de Odoo.
        """

        start = datetime.combine(holiday_date, time.min)
        end = datetime.combine(holiday_date, time.max).replace(
            microsecond=0,
        )

        return start, end

    def _holiday_exists(self, Holiday, start, end):
        """Comprueba si ya existe un feriado global en el rango indicado."""

        overlap_domain = [
            ("resource_id", "=", False),
            ("date_from", "<=", fields.Datetime.to_string(end)),
            ("date_to", ">=", fields.Datetime.to_string(start)),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.env.company.id),
        ]

        return bool(Holiday.search_count(overlap_domain))

    def action_generate(self):
        self.ensure_one()

        if self.year < 1900 or self.year > 2200:
            raise ValidationError(
                _("Ingrese un año válido entre 1900 y 2200.")
            )

        Holiday = self.env["resource.calendar.leaves"].sudo()

        created = 0
        skipped = 0

        for (
            holiday_date,
            name,
            mandatory,
            holiday_type,
        ) in self._holiday_values():

            start, end = self._prepare_holiday_datetimes(
                holiday_date
            )

            if self._holiday_exists(Holiday, start, end):
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
                "message": _(
                    "Creados: %(created)s. "
                    "Existentes omitidos: %(skipped)s.",
                    created=created,
                    skipped=skipped,
                ),
                "type": "success",
                "sticky": False,
            },
        }
