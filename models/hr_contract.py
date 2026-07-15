# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrContract(models.Model):
    _inherit = "hr.contract"

    cr_pay_frequency = fields.Selection(
        [
            ("weekly", "Semanal"),
            ("biweekly", "Quincenal"),
            ("monthly", "Mensual"),
            ("hourly", "Por hora"),
            ("daily", "Por día"),
        ],
        string="Frecuencia de pago Costa Rica",
        default="biweekly",
        required=True,
        tracking=True,
    )

    cr_journey_type = fields.Selection(
        [
            ("day", "Diurna"),
            ("mixed", "Mixta"),
            ("night", "Nocturna"),
            ("partial", "Parcial"),
            ("rotating", "Rotativa"),
            ("route", "Por ruta"),
        ],
        string="Tipo de jornada",
        default="day",
        required=True,
        tracking=True,
    )

    cr_salary_mode = fields.Selection(
        [
            ("fixed", "Salario fijo"),
            ("hourly", "Salario por hora"),
            ("daily", "Salario por día"),
            ("mixed", "Salario mixto"),
        ],
        string="Modalidad salarial",
        default="fixed",
        required=True,
        tracking=True,
    )

    cr_hours_per_day = fields.Float(
        string="Horas ordinarias por día",
        default=8.0,
        required=True,
    )

    cr_days_divisor = fields.Float(
        string="Divisor para salario diario",
        default=30.0,
        required=True,
        help="Divisor utilizado para obtener el salario diario desde el salario mensual.",
    )

    cr_allow_advanced_leave = fields.Boolean(
        string="Permitir vacaciones adelantadas",
        help="Permite gestionar saldos negativos de vacaciones cuando la empresa lo autorice.",
    )

    cr_structure_id = fields.Many2one(
        "hr.payroll.structure",
        string="Estructura salarial aplicada",
        compute="_compute_cr_structure_id",
        store=False,
        help="Estructura ordinaria sugerida según la frecuencia de pago del contrato.",
    )

    @api.depends("cr_pay_frequency", "structure_type_id")
    def _compute_cr_structure_id(self):
        xmlids = {
            "monthly": "l10n_cr_hr.structure_monthly",
            "biweekly": "l10n_cr_hr.structure_biweekly",
            "weekly": "l10n_cr_hr.structure_weekly",
            "hourly": "l10n_cr_hr.structure_hourly",
            "daily": "l10n_cr_hr.structure_hourly",
        }
        for contract in self:
            structure = self.env.ref(
                xmlids.get(contract.cr_pay_frequency, ""),
                raise_if_not_found=False,
            )
            contract.cr_structure_id = structure
