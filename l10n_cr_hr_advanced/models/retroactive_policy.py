# -*- coding: utf-8 -*-
from odoo import fields, models


class CrPayrollRetroactiveRulePolicy(models.Model):
    _name = "cr.payroll.retroactive.rule.policy"
    _description = "Política de recálculo retroactivo por regla salarial CR"
    _order = "company_id, salary_rule_id"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    salary_rule_id = fields.Many2one(
        "hr.salary.rule",
        string="Regla salarial",
        required=True,
        ondelete="cascade",
    )
    policy = fields.Selection([
        ("exclude", "Excluir del recálculo"),
        ("proportional_wage", "Recalcular proporcionalmente al salario"),
        ("fixed", "Mantener importe original"),
    ], string="Tratamiento retroactivo", required=True, default="exclude")
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Observaciones")

    _sql_constraints = [
        (
            "cr_retro_policy_company_rule_uniq",
            "unique(company_id,salary_rule_id)",
            "Ya existe una política retroactiva para esta regla y compañía.",
        ),
    ]
