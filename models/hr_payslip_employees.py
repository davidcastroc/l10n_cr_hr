# -*- coding: utf-8 -*-

from odoo import api, models, _
from odoo.exceptions import ValidationError


class HrPayslipEmployees(models.TransientModel):
    _inherit = "hr.payslip.employees"

    @api.onchange("structure_id")
    def _onchange_structure_id_cr_filter(self):
        """
        Filtra los empleados del asistente según la estructura salarial
        específica configurada en el contrato activo.

        Ejemplo:
        - CR - Nómina semanal -> solo contratos con esa estructura.
        - CR - Nómina quincenal -> solo contratos con esa estructura.
        """
        for wizard in self:
            if not wizard.structure_id:
                continue

            contracts = self.env["hr.contract"].search([
                ("state", "=", "open"),
                ("cr_payroll_structure_id", "=", wizard.structure_id.id),
            ])

            wizard.employee_ids = [(6, 0, contracts.mapped("employee_id").ids)]

    def compute_sheet(self):
        """
        Validación adicional antes de generar recibos para evitar que
        entren empleados cuya estructura contractual no coincide con
        la estructura seleccionada en el lote.
        """
        for wizard in self:
            if not wizard.structure_id:
                continue

            invalid_employees = wizard.employee_ids.filtered(
                lambda employee:
                    employee.contract_id
                    and employee.contract_id.cr_payroll_structure_id
                    and employee.contract_id.cr_payroll_structure_id
                    != wizard.structure_id
            )

            if invalid_employees:
                raise ValidationError(_(
                    "Los siguientes empleados no pertenecen a la estructura "
                    "salarial seleccionada:\n%s"
                ) % "\n".join(invalid_employees.mapped("name")))

        return super().compute_sheet()
