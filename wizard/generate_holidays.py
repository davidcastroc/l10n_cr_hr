# -*- coding: utf-8 -*-

from datetime import date, datetime, time, timedelta

import pytz

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

        return sorted(
            holidays,
            key=lambda item: item[0],
        )

    def _prepare_holiday_datetimes(
        self,
        holiday_date,
    ):
        """Construye el feriado completo en hora de Costa Rica.

        resource.calendar.leaves utiliza campos Datetime
        almacenados internamente en UTC.

        Los feriados se representan como intervalos
        semiabiertos [inicio, fin):

            00:00:00 Costa Rica
            hasta
            00:00:00 Costa Rica del día siguiente

        Por ejemplo:

            2026-05-01 00:00:00 CR
            ->
            2026-05-02 00:00:00 CR

        En UTC:

            2026-05-01 06:00:00 UTC
            ->
            2026-05-02 06:00:00 UTC

        Usar la medianoche del día siguiente evita dejar
        un segundo residual al final del feriado. Ese segundo
        residual puede ser interpretado por la generación
        estándar de Work Entries como tiempo laborable.
        """

        costa_rica_tz = pytz.timezone(
            "America/Costa_Rica"
        )

        local_start = costa_rica_tz.localize(
            datetime.combine(
                holiday_date,
                time.min,
            )
        )

        local_end = costa_rica_tz.localize(
            datetime.combine(
                holiday_date + timedelta(days=1),
                time.min,
            )
        )

        utc_start = (
            local_start
            .astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )

        utc_end = (
            local_end
            .astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )

        return utc_start, utc_end

    def _holiday_exists(
        self,
        Holiday,
        start,
        end,
    ):
        """Comprueba si ya existe el mismo feriado legal CR.

        La búsqueda se restringe a registros marcados
        explícitamente como feriados legales de Costa Rica.

        Los feriados utilizan intervalos semiabiertos
        [inicio, fin), por lo que dos feriados consecutivos
        pueden compartir la frontera temporal sin que exista
        una superposición real.

        Existe intersección únicamente cuando:

            existing.date_from < end
            existing.date_to > start
        """

        overlap_domain = [
            ("resource_id", "=", False),
            ("cr_is_public_holiday", "=", True),
            (
                "date_from",
                "<",
                fields.Datetime.to_string(end),
            ),
            (
                "date_to",
                ">",
                fields.Datetime.to_string(start),
            ),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.env.company.id),
        ]

        return bool(
            Holiday.search_count(
                overlap_domain
            )
        )

    def action_generate(self):
        self.ensure_one()

        if (
            self.year < 1900
            or self.year > 2200
        ):
            raise ValidationError(
                _(
                    "Ingrese un año válido entre "
                    "1900 y 2200."
                )
            )

        Holiday = (
            self.env[
                "resource.calendar.leaves"
            ]
            .sudo()
        )

        public_holiday_type = (
            self.env[
                "hr.work.entry.type"
            ]
            .sudo()
            .search(
                [
                    (
                        "code",
                        "=",
                        "CR_PUBLIC_HOLIDAY",
                    ),
                ],
                limit=1,
            )
        )

        if not public_holiday_type:
            raise ValidationError(
                _(
                    "No existe el tipo de entrada "
                    "de trabajo CR_PUBLIC_HOLIDAY."
                )
            )

        created = 0
        skipped = 0

        for (
            holiday_date,
            name,
            mandatory,
            holiday_type,
        ) in self._holiday_values():

            start, end = (
                self._prepare_holiday_datetimes(
                    holiday_date
                )
            )

            if self._holiday_exists(
                Holiday,
                start,
                end,
            ):
                skipped += 1
                continue

            Holiday.create({
                "name":
                    "CR - %s" % name,

                "date_from":
                    fields.Datetime.to_string(
                        start
                    ),

                "date_to":
                    fields.Datetime.to_string(
                        end
                    ),

                "company_id":
                    self.env.company.id,

                "calendar_id":
                    False,

                "resource_id":
                    False,

                "work_entry_type_id":
                    public_holiday_type.id,

                "time_type":
                    "leave",

                "cr_is_public_holiday":
                    True,

                "cr_mandatory_pay":
                    mandatory,

                "cr_holiday_type":
                    holiday_type,

                "cr_legal_source":
                    "Código de Trabajo / MTSS",
            })

            created += 1

        return {
            "type":
                "ir.actions.client",

            "tag":
                "display_notification",

            "params": {
                "title":
                    _("Feriados de Costa Rica"),

                "message":
                    _(
                        "Creados: %(created)s. "
                        "Existentes omitidos: "
                        "%(skipped)s.",
                        created=created,
                        skipped=skipped,
                    ),

                "type":
                    "success",

                "sticky":
                    False,
            },
        }