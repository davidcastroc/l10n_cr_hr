# -*- coding: utf-8 -*-

from datetime import date, datetime, time, timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class CrGenerateHolidaysWizard(models.TransientModel):
    _name = "cr.generate.holidays.wizard"
    _description = "Generar feriados de Costa Rica"

    year = fields.Integer(
        string="Año",
        required=True,
        default=lambda self: fields.Date.today().year,
    )

    def _easter_sunday(self, year):
        """Calcula el Domingo de Resurrección."""
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + (2 * e) + (2 * i) - h - k) % 7
        m = (a + (11 * h) + (22 * l)) // 451
        month = (h + l - (7 * m) + 114) // 31
        day = ((h + l - (7 * m) + 114) % 31) + 1

        return date(year, month, day)

    def _get_holidays(self):
        self.ensure_one()

        easter = self._easter_sunday(self.year)

        holidays = [
            (date(self.year, 1, 1), _("Año Nuevo"), True, "fixed"),
            (
                date(self.year, 4, 11),
                _("Día de Juan Santamaría"),
                True,
                "fixed",
            ),
            (
                easter - timedelta(days=3),
                _("Jueves Santo"),
                True,
                "movable",
            ),
            (
                easter - timedelta(days=2),
                _("Viernes Santo"),
                True,
                "movable",
            ),
            (
                date(self.year, 5, 1),
                _("Día Internacional del Trabajo"),
                True,
                "fixed",
            ),
            (
                date(self.year, 7, 25),
                _("Anexión del Partido de Nicoya"),
                True,
                "fixed",
            ),
            (
                date(self.year, 8, 2),
                _("Día de la Virgen de los Ángeles"),
                False,
                "fixed",
            ),
            (
                date(self.year, 8, 15),
                _("Día de la Madre"),
                True,
                "fixed",
            ),
            (
                date(self.year, 8, 31),
                _("Día de la Persona Negra y la Cultura Afrocostarricense"),
                False,
                "fixed",
            ),
            (
                date(self.year, 9, 15),
                _("Día de la Independencia"),
                True,
                "fixed",
            ),
            (
                date(self.year, 12, 1),
                _("Día de la Abolición del Ejército"),
                False,
                "fixed",
            ),
            (
                date(self.year, 12, 25),
                _("Navidad"),
                True,
                "fixed",
            ),
        ]

        return holidays

    def _holiday_exists(self, company, date_from, date_to):
        """Detecta cualquier día festivo nativo que traslape el periodo."""
        domain = [
            ("resource_id", "=", False),
            ("date_from", "<=", fields.Datetime.to_string(date_to)),
            ("date_to", ">=", fields.Datetime.to_string(date_from)),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", company.id),
        ]

        return bool(
            self.env["resource.calendar.leaves"]
            .sudo()
            .search_count(domain)
        )

    def action_generate(self):
        self.ensure_one()

        if self.year < 2000 or self.year > 2100:
            raise UserError(_("El año indicado no es válido."))

        company = self.env.company
        Holiday = self.env["resource.calendar.leaves"].sudo()

        created = 0
        skipped = 0

        for holiday_date, name, mandatory, holiday_type in self._get_holidays():
            date_from = datetime.combine(holiday_date, time.min)
            date_to = datetime.combine(holiday_date, time.max)

            if self._holiday_exists(company, date_from, date_to):
                skipped += 1
                continue

            Holiday.create({
                "name": "CR - %s" % name,
                "date_from": fields.Datetime.to_string(date_from),
                "date_to": fields.Datetime.to_string(date_to),
                "company_id": company.id,
                "calendar_id": False,
                "resource_id": False,
                "cr_is_public_holiday": True,
                "cr_mandatory_pay": mandatory,
                "cr_holiday_type": holiday_type,
                "cr_legal_source": "Código de Trabajo de Costa Rica",
            })

            created += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Feriados de Costa Rica"),
                "message": _(
                    "Feriados creados: %(created)s. "
                    "Feriados existentes omitidos: %(skipped)s.",
                    created=created,
                    skipped=skipped,
                ),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window_close",
                },
            },
        }