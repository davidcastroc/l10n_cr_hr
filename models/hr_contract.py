# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrPayrollStructure(models.Model):
    _inherit = "hr.payroll.structure"

    cr_structure_usage = fields.Selection(
        selection=[
            ("weekly", "Nómina semanal"),
            ("biweekly", "Nómina quincenal"),
            ("monthly", "Nómina mensual"),
            ("hourly", "Nómina por horas"),
            ("daily", "Nómina diaria"),
            ("extraordinary", "Pago extraordinario"),
            ("aguinaldo", "Aguinaldo"),
            ("termination", "Liquidación laboral"),
            ("other", "Otro"),
        ],
        string="Uso de estructura CR",
        help=(
            "Define para qué proceso de Nómina Costa Rica se utiliza "
            "esta estructura salarial."
        ),
    )

    cr_is_regular_payroll = fields.Boolean(
        string="Estructura ordinaria CR",
        compute="_compute_cr_is_regular_payroll",
        store=True,
        help=(
            "Indica si esta estructura puede asignarse como estructura "
            "ordinaria de un contrato."
        ),
    )

    @api.depends("cr_structure_usage")
    def _compute_cr_is_regular_payroll(self):
        regular_usages = {
            "weekly",
            "biweekly",
            "monthly",
            "hourly",
            "daily",
        }

        for structure in self:
            structure.cr_is_regular_payroll = (
                structure.cr_structure_usage in regular_usages
            )


class HrContract(models.Model):
    _inherit = "hr.contract"

    cr_pay_frequency = fields.Selection(
        selection=[
            ("weekly", "Semanal"),
            ("biweekly", "Quincenal"),
            ("monthly", "Mensual"),
            ("hourly", "Por hora"),
            ("daily", "Por día"),
        ],
        string="Frecuencia de pago",
        default="monthly",
        required=True,
        help="Periodicidad con la que se generan y pagan los recibos de nómina.",
    )

    cr_payroll_structure_id = fields.Many2one(
        comodel_name="hr.payroll.structure",
        string="Estructura salarial CR",
        domain=(
            "["
            "('type_id', '=', structure_type_id), "
            "('cr_is_regular_payroll', '=', True), "
            "('cr_structure_usage', '=', cr_pay_frequency)"
            "]"
        ),
        help=(
            "Estructura salarial ordinaria utilizada para procesar "
            "la nómina de este contrato."
        ),
    )

    cr_salary_mode = fields.Selection(
        selection=[
            ("fixed", "Salario fijo"),
            ("hourly", "Por hora"),
            ("daily", "Por día"),
            ("mixed", "Mixto"),
        ],
        string="Modalidad salarial",
        default="fixed",
        required=True,
        help="Forma utilizada para determinar el salario del colaborador.",
    )

    cr_journey_type = fields.Selection(
        selection=[
            ("day", "Diurna"),
            ("mixed", "Mixta"),
            ("night", "Nocturna"),
            ("partial", "Diurna medio tiempo"),
            ("rotating", "Rotativa"),
            ("route", "Ruta"),
        ],
        string="Tipo de jornada",
        default="day",
        required=True,
        help="Tipo de jornada laboral aplicable al contrato.",
    )

    cr_hours_per_day = fields.Float(
        string="Horas por día",
        default=8.0,
        required=True,
        help="Cantidad ordinaria de horas laboradas por día.",
    )

    cr_days_divisor = fields.Float(
        string="Divisor de salario diario",
        default=30.0,
        required=True,
        help=(
            "Divisor utilizado para obtener el salario diario a partir "
            "del salario mensual."
        ),
    )

    cr_allow_advanced_leave = fields.Boolean(
        string="Permitir vacaciones adelantadas",
        default=False,
        help=(
            "Permite asignar vacaciones aunque el colaborador todavía "
            "no tenga saldo acumulado suficiente."
        ),
    )

    @api.onchange("cr_pay_frequency", "structure_type_id")
    def _onchange_cr_payroll_structure(self):
        for contract in self:
            contract.cr_payroll_structure_id = False

            if not contract.cr_pay_frequency:
                continue

            domain = [
                ("cr_structure_usage", "=", contract.cr_pay_frequency),
                ("cr_is_regular_payroll", "=", True),
            ]

            if contract.structure_type_id:
                domain.append(
                    ("type_id", "=", contract.structure_type_id.id)
                )

            structure = self.env["hr.payroll.structure"].search(
                domain,
                limit=1,
            )

            if structure:
                contract.cr_payroll_structure_id = structure

    @api.constrains(
        "cr_pay_frequency",
        "cr_payroll_structure_id",
        "structure_type_id",
    )
    def _check_cr_payroll_structure(self):
        for contract in self:
            structure = contract.cr_payroll_structure_id

            if not structure:
                continue

            if not structure.cr_is_regular_payroll:
                raise ValidationError(
                    _(
                        "La estructura salarial '%s' no puede utilizarse "
                        "como estructura ordinaria de un contrato."
                    )
                    % structure.display_name
                )

            if (
                structure.cr_structure_usage
                != contract.cr_pay_frequency
            ):
                raise ValidationError(
                    _(
                        "La frecuencia de pago del contrato no coincide "
                        "con la estructura salarial seleccionada."
                    )
                )

            if (
                contract.structure_type_id
                and structure.type_id
                != contract.structure_type_id
            ):
                raise ValidationError(
                    _(
                        "La estructura salarial seleccionada no pertenece "
                        "al tipo de estructura salarial del contrato."
                    )
                )

    @api.constrains("cr_hours_per_day")
    def _check_cr_hours_per_day(self):
        for contract in self:
            if contract.cr_hours_per_day <= 0:
                raise ValidationError(
                    _("Las horas por día deben ser mayores que cero.")
                )

            if contract.cr_hours_per_day > 24:
                raise ValidationError(
                    _("Las horas por día no pueden ser mayores que 24.")
                )

    @api.constrains("cr_days_divisor")
    def _check_cr_days_divisor(self):
        for contract in self:
            if contract.cr_days_divisor <= 0:
                raise ValidationError(
                    _("El divisor de salario diario debe ser mayor que cero.")
                )