# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CrPayrollTaxDependent(models.Model):
    _name = "cr.payroll.tax.dependent"
    _description = "Dependiente fiscal de nómina"
    _order = "employee_id, dependent_type, name"

    name = fields.Char(string="Nombre completo", required=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado",
        required=True,
        ondelete="cascade",
        index=True,
    )
    identification = fields.Char(string="Identificación")
    dependent_type = fields.Selection(
        [("child", "Hijo(a)"), ("spouse", "Cónyuge")],
        string="Tipo de dependiente",
        required=True,
    )
    date_from = fields.Date(string="Vigente desde")
    date_to = fields.Date(string="Vigente hasta")
    active = fields.Boolean(string="Activo", default=True)
    notes = fields.Text(string="Observaciones")


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    cr_identification_type = fields.Selection(
        [
            ("01", "Cédula física"),
            ("02", "Cédula jurídica"),
            ("03", "DIMEX"),
            ("04", "NITE"),
        ],
        string="Tipo de identificación CR",
    )
    cr_social_security_number = fields.Char(string="Número de asegurado CCSS")

    cr_tax_dependent_ids = fields.One2many(
        "cr.payroll.tax.dependent",
        "employee_id",
        string="Dependientes fiscales",
    )
    cr_tax_children = fields.Integer(
        string="Hijos para crédito fiscal",
        compute="_compute_cr_tax_dependents",
        store=True,
        readonly=False,
    )
    cr_tax_spouse = fields.Boolean(
        string="Crédito fiscal por cónyuge",
        compute="_compute_cr_tax_dependents",
        store=True,
        readonly=False,
    )

    cr_vacation_opening_days = fields.Float(
        string="Saldo inicial de vacaciones (días)",
        help="Saldo migrado al inicio de la implementación. La asignación oficial debe registrarse también en Vacaciones.",
    )
    cr_vacation_opening_date = fields.Date(string="Fecha de corte de vacaciones")
    cr_aguinaldo_opening_earnings = fields.Monetary(
        string="Remuneraciones acumuladas para aguinaldo",
        currency_field="currency_id",
        help="Suma histórica de remuneraciones computables del período legal anterior a la primera nómina procesada en Odoo.",
    )
    cr_aguinaldo_opening_days = fields.Float(
        string="Días informativos acumulados de aguinaldo",
        help="Campo informativo para migraciones. El cálculo legal se basa en remuneraciones computables, no en días.",
    )
    cr_aguinaldo_opening_date = fields.Date(string="Fecha de corte de aguinaldo")
    cr_opening_notes = fields.Text(string="Observaciones de saldos iniciales")

    cr_payroll_deduction_ids = fields.One2many(
        "cr.payroll.deduction",
        "employee_id",
        string="Deducciones recurrentes",
    )

    @api.depends(
        "cr_tax_dependent_ids.active",
        "cr_tax_dependent_ids.dependent_type",
        "cr_tax_dependent_ids.date_from",
        "cr_tax_dependent_ids.date_to",
    )
    def _compute_cr_tax_dependents(self):
        today = fields.Date.context_today(self)
        for employee in self:
            valid = employee.cr_tax_dependent_ids.filtered(
                lambda dep: dep.active
                and (not dep.date_from or dep.date_from <= today)
                and (not dep.date_to or dep.date_to >= today)
            )
            employee.cr_tax_children = len(valid.filtered(lambda dep: dep.dependent_type == "child"))
            employee.cr_tax_spouse = bool(valid.filtered(lambda dep: dep.dependent_type == "spouse"))
