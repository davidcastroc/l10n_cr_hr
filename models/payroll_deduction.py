# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CrPayrollDeduction(models.Model):
    _name = "cr.payroll.deduction"
    _description = "Deducción recurrente de nómina CR"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority, employee_id, date_from"

    name = fields.Char(
        string="Descripción",
        required=True,
        tracking=True,
    )

    employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado",
        required=True,
        index=True,
        tracking=True,
    )

    deduction_type = fields.Selection(
        [
            ("alimony", "Pensión alimentaria"),
            ("garnishment", "Embargo salarial"),
            ("popular_credit", "Crédito Banco Popular"),
            ("loan", "Préstamo interno"),
            ("advance", "Adelanto salarial"),
            ("solidarity", "Asociación solidarista"),
            ("cooperative", "Cooperativa"),
            ("savings", "Ahorro"),
            ("insurance", "Seguro"),
            ("other", "Otra deducción"),
        ],
        string="Tipo de deducción",
        required=True,
        tracking=True,
    )

    calculation = fields.Selection(
        [
            ("fixed", "Monto fijo"),
            ("percent", "Porcentaje"),
        ],
        string="Forma de cálculo",
        default="fixed",
        required=True,
        tracking=True,
    )

    amount = fields.Monetary(
        string="Cuota o monto",
        currency_field="currency_id",
        tracking=True,
    )

    percentage = fields.Float(
        string="Porcentaje",
        digits=(8, 5),
        tracking=True,
    )

    original_amount = fields.Monetary(
        string="Monto original",
        currency_field="currency_id",
    )

    balance = fields.Monetary(
        string="Saldo pendiente",
        currency_field="currency_id",
        tracking=True,
    )

    currency_id = fields.Many2one(
        "res.currency",
        related="employee_id.company_id.currency_id",
        store=True,
    )

    date_from = fields.Date(
        string="Vigente desde",
        required=True,
        tracking=True,
    )

    date_to = fields.Date(
        string="Vigente hasta",
        tracking=True,
    )

    priority = fields.Integer(
        string="Prioridad",
        default=50,
    )

    frequency = fields.Selection(
        [
            ("weekly", "Semanal"),
            ("biweekly", "Quincenal"),
            ("monthly", "Mensual"),
            ("each", "Cada recibo"),
        ],
        string="Frecuencia",
        default="each",
        required=True,
        tracking=True,
        help=(
            "Cada recibo: se aplica en todos los recibos.\n"
            "Semanal: se aplica en todos los recibos de contratos semanales.\n"
            "Quincenal: se aplica en ambas quincenas de contratos quincenales.\n"
            "Mensual: se aplica una sola vez por mes."
        ),
    )

    application_moment = fields.Selection(
        [
            ("any", "Primer recibo procesado del mes"),
            ("first_half", "Primera quincena del mes"),
            ("second_half", "Segunda quincena del mes"),
        ],
        string="Momento de aplicación",
        default="any",
        required=True,
        tracking=True,
        help=(
            "Disponible para deducciones mensuales.\n"
            "Primer recibo procesado: se aplica en el primer recibo cerrado "
            "durante el mes.\n"
            "Primera quincena: solamente se aplica en el recibo que finaliza "
            "entre los días 1 y 15.\n"
            "Segunda quincena: solamente se aplica en el recibo que inicia "
            "a partir del día 16."
        ),
    )

    court_file = fields.Char(
        string="Expediente / referencia",
    )

    beneficiary = fields.Char(
        string="Beneficiario",
    )

    active = fields.Boolean(
        default=True,
        tracking=True,
    )

    notes = fields.Text(
        string="Observaciones",
    )

    movement_ids = fields.One2many(
        "cr.payroll.deduction.movement",
        "deduction_id",
        string="Movimientos",
        readonly=True,
    )

    @api.constrains(
        "amount",
        "percentage",
        "balance",
        "original_amount",
    )
    def _check_amounts(self):
        for rec in self:
            values = (
                rec.amount,
                rec.percentage,
                rec.balance,
                rec.original_amount,
            )

            if any(value < 0 for value in values):
                raise ValidationError(
                    _(
                        "Los montos, porcentajes y saldos "
                        "no pueden ser negativos."
                    )
                )

            if rec.calculation == "fixed" and not rec.amount:
                raise ValidationError(
                    _(
                        "Una deducción fija debe tener una "
                        "cuota mayor que cero."
                    )
                )

            if (
                rec.calculation == "percent"
                and rec.percentage > 100
            ):
                raise ValidationError(
                    _(
                        "El porcentaje de deducción no puede "
                        "superar el 100 %."
                    )
                )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if (
                rec.date_from
                and rec.date_to
                and rec.date_to < rec.date_from
            ):
                raise ValidationError(
                    _(
                        "La fecha final no puede ser anterior "
                        "a la fecha inicial."
                    )
                )

    @api.constrains("frequency", "application_moment")
    def _check_application_moment(self):
        for rec in self:
            if (
                rec.frequency != "monthly"
                and rec.application_moment != "any"
            ):
                raise ValidationError(
                    _(
                        "El momento de aplicación por quincena "
                        "solo puede utilizarse con frecuencia Mensual."
                    )
                )

    @api.onchange("original_amount")
    def _onchange_original_amount(self):
        if self.original_amount and not self.balance:
            self.balance = self.original_amount

    @api.onchange("frequency")
    def _onchange_frequency(self):
        """Restablece el momento cuando la frecuencia no es mensual."""
        if self.frequency != "monthly":
            self.application_moment = "any"

    def _already_applied_in_month(self, payslip):
        """Indica si esta deducción ya fue aplicada durante el mes.

        La validación usa los movimientos confirmados para impedir que una
        deducción mensual sea cargada dos veces, incluso si se recalcula un
        recibo o se procesa otro recibo del mismo mes.
        """
        self.ensure_one()

        if not payslip.date_to:
            return False

        month_start = payslip.date_to.replace(day=1)

        return bool(
            self.env[
                "cr.payroll.deduction.movement"
            ].search_count(
                [
                    ("deduction_id", "=", self.id),
                    ("state", "=", "applied"),
                    ("date", ">=", month_start),
                    ("date", "<=", payslip.date_to),
                    ("payslip_id", "!=", payslip.id),
                ]
            )
        )

    def _matches_monthly_application_moment(self, payslip):
        """Valida en cuál quincena debe aplicarse la deducción mensual."""
        self.ensure_one()

        if not payslip.date_from or not payslip.date_to:
            return False

        if self.application_moment == "first_half":
            return payslip.date_to.day <= 15

        if self.application_moment == "second_half":
            return payslip.date_from.day >= 16

        return True

    def applies_to_payslip(self, payslip):
        """Determina si la deducción corresponde al recibo indicado."""
        self.ensure_one()

        if not payslip or not payslip.contract_id:
            return False

        if not payslip.date_from or not payslip.date_to:
            return False

        # La deducción debe estar activa y vigente en el período.
        if not self.active:
            return False

        if self.date_from and payslip.date_to < self.date_from:
            return False

        if self.date_to and payslip.date_from > self.date_to:
            return False

        # Cada recibo: aplica en cualquier frecuencia contractual.
        if self.frequency == "each":
            return True

        # Semanal: aplica en cada recibo de un contrato semanal.
        if self.frequency == "weekly":
            return (
                payslip.contract_id.cr_pay_frequency
                == "weekly"
            )

        # Quincenal: aplica en ambas quincenas de un contrato quincenal.
        if self.frequency == "biweekly":
            return (
                payslip.contract_id.cr_pay_frequency
                == "biweekly"
            )

        # Mensual: aplica solo una vez por mes y según el momento elegido.
        if self.frequency == "monthly":
            if not self._matches_monthly_application_moment(
                payslip
            ):
                return False

            return not self._already_applied_in_month(
                payslip
            )

        return True

    def amount_for_period(self, base, payslip=None):
        """Calcula el monto aplicable de la deducción."""
        self.ensure_one()

        if (
            payslip
            and not self.applies_to_payslip(payslip)
        ):
            return 0.0

        if self.calculation == "fixed":
            amount = self.amount
        else:
            amount = (
                max(base or 0.0, 0.0)
                * self.percentage
                / 100.0
            )

        # Cuando existe saldo pendiente, nunca rebaja más que el saldo.
        # Si el saldo está vacío o en cero, se considera indefinida.
        if self.balance:
            amount = min(amount, self.balance)

        return max(amount, 0.0)