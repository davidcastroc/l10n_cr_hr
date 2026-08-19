# -*- coding: utf-8 -*-
import base64
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    cr_process_type = fields.Selection(
        [
            ("ordinary", "Nómina ordinaria"),
            ("aguinaldo", "Aguinaldo"),
            ("extraordinary", "Pago extraordinario"),
            ("settlement", "Liquidación laboral"),
        ],
        string="Tipo de proceso Costa Rica",
        default="ordinary",
        required=True,
    )
    cr_is_aguinaldo = fields.Boolean(
        string="Es aguinaldo",
        compute="_compute_cr_flags",
        store=True,
    )

    cr_employee_count = fields.Integer(string="Colaboradores", compute="_compute_cr_dashboard")
    cr_basic_total = fields.Monetary(string="Salario básico", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_gross_total = fields.Monetary(string="Salario bruto", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_employee_ccss_total = fields.Monetary(string="CCSS trabajador", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_income_tax_total = fields.Monetary(string="Renta", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_recurring_deduction_total = fields.Monetary(string="Deducciones recurrentes", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_total_deductions = fields.Monetary(string="Deducciones totales", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_net_total = fields.Monetary(string="Total neto por pagar", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_employer_social_total = fields.Monetary(string="Cargas patronales", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_aguinaldo_period_total = fields.Monetary(string="Provisión aguinaldo", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_aguinaldo_accumulated_total = fields.Monetary(string="Aguinaldo acumulado", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_vacation_provision_total = fields.Monetary(string="Provisión vacaciones", compute="_compute_cr_dashboard", currency_field="currency_id")
    cr_employer_cost_total = fields.Monetary(string="Costo patronal total", compute="_compute_cr_dashboard", currency_field="currency_id")

    @api.depends(
        "cr_process_type",
        "slip_ids.state",
        "slip_ids.line_ids.total",
        "slip_ids.line_ids.code",
        "slip_ids.line_ids.category_id.code",
    )
    def _compute_cr_flags(self):
        for run in self:
            run.cr_is_aguinaldo = run.cr_process_type == "aguinaldo"

    @api.depends(
        "slip_ids.state",
        "slip_ids.cr_basic_total",
        "slip_ids.cr_gross_total",
        "slip_ids.cr_employee_ccss_total",
        "slip_ids.cr_income_tax_total",
        "slip_ids.cr_recurring_deduction_total",
        "slip_ids.cr_total_deductions",
        "slip_ids.cr_net_total",
        "slip_ids.cr_employer_social_total",
        "slip_ids.cr_aguinaldo_period_total",
        "slip_ids.cr_aguinaldo_accumulated",
        "slip_ids.cr_vacation_provision_total",
        "slip_ids.cr_employer_cost_total",
    )
    def _compute_cr_dashboard(self):
        for run in self:
            slips = run.slip_ids.filtered(lambda slip: slip.state != "cancel")
            run.cr_employee_count = len(slips)
            run.cr_basic_total = sum(slips.mapped("cr_basic_total"))
            run.cr_gross_total = sum(slips.mapped("cr_gross_total"))
            run.cr_employee_ccss_total = sum(slips.mapped("cr_employee_ccss_total"))
            run.cr_income_tax_total = sum(slips.mapped("cr_income_tax_total"))
            run.cr_recurring_deduction_total = sum(slips.mapped("cr_recurring_deduction_total"))
            run.cr_total_deductions = sum(slips.mapped("cr_total_deductions"))
            run.cr_net_total = sum(slips.mapped("cr_net_total"))
            run.cr_employer_social_total = sum(slips.mapped("cr_employer_social_total"))
            run.cr_aguinaldo_period_total = sum(slips.mapped("cr_aguinaldo_period_total"))
            run.cr_aguinaldo_accumulated_total = sum(slips.mapped("cr_aguinaldo_accumulated"))
            run.cr_vacation_provision_total = sum(slips.mapped("cr_vacation_provision_total"))
            run.cr_employer_cost_total = sum(slips.mapped("cr_employer_cost_total"))

    def action_cr_validate_payroll(self):
        self.ensure_one()
        issues = []
        for slip in self.slip_ids:
            if slip.cr_validation_message:
                issues.append("%s: %s" % (
                    slip.employee_id.name,
                    slip.cr_validation_message.replace("\n", "; "),
                ))
        if issues:
            raise UserError(_("La nómina tiene bloqueos:\n%s") % "\n".join(issues))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Validación de nómina"),
                "message": _("Todos los recibos del lote pasaron las validaciones."),
                "type": "success",
                "sticky": False,
            },
        }

    def _cr_csv_attachment(self, filename, headers, rows):
        self.ensure_one()
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        writer.writerows(rows)
        payload = "\ufeff" + stream.getvalue()
        attachment = self.env["ir.attachment"].sudo().create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(payload.encode("utf-8")),
            "mimetype": "text/csv",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def _cr_export_slips(self):
        self.ensure_one()
        return self.slip_ids.filtered(lambda slip: slip.state != "cancel").sorted(
            key=lambda slip: (slip.employee_id.name or "", slip.id)
        )

    def action_cr_download_summary(self):
        self.ensure_one()
        headers = [
            "Identificación", "Empleado", "Salario básico", "Salario bruto",
            "CCSS trabajador", "Renta", "Deducciones recurrentes",
            "Deducciones totales", "Salario neto", "Cargas patronales",
            "Provisión aguinaldo", "Aguinaldo acumulado",
            "Provisión vacaciones", "Costo patronal",
        ]
        rows = []
        for slip in self._cr_export_slips():
            rows.append([
                slip.employee_id.identification_id or "",
                slip.employee_id.name or "",
                slip.cr_basic_total,
                slip.cr_gross_total,
                slip.cr_employee_ccss_total,
                slip.cr_income_tax_total,
                slip.cr_recurring_deduction_total,
                slip.cr_total_deductions,
                slip.cr_net_total,
                slip.cr_employer_social_total,
                slip.cr_aguinaldo_period_total,
                slip.cr_aguinaldo_accumulated,
                slip.cr_vacation_provision_total,
                slip.cr_employer_cost_total,
            ])
        rows.append(["", "TOTALES", self.cr_basic_total, self.cr_gross_total,
                     self.cr_employee_ccss_total, self.cr_income_tax_total,
                     self.cr_recurring_deduction_total, self.cr_total_deductions,
                     self.cr_net_total, self.cr_employer_social_total,
                     self.cr_aguinaldo_period_total, self.cr_aguinaldo_accumulated_total,
                     self.cr_vacation_provision_total, self.cr_employer_cost_total])
        return self._cr_csv_attachment("Resumen_%s.csv" % (self.name or self.id), headers, rows)

    def action_cr_download_ccss(self):
        self.ensure_one()
        headers = [
            "Identificación", "Empleado", "Salario reportable",
            "SEM trabajador", "IVM trabajador", "Banco Popular trabajador",
            "Total trabajador", "SEM patrono", "IVM patrono",
            "Banco Popular patrono", "Asignaciones familiares", "IMAS", "INA",
            "FCL", "ROP", "Total patronal",
        ]
        rows = []
        for slip in self._cr_export_slips():
            def line(code):
                return abs(sum(slip.line_ids.filtered(lambda item: item.code == code).mapped("total")))
            sem_emp = line("CR_SEM_EMP")
            ivm_emp = line("CR_IVM_EMP")
            bp_emp = line("CR_BP_EMP")
            sem_pat = line("CR_SEM_PAT")
            ivm_pat = line("CR_IVM_PAT")
            bp_pat = line("CR_BP_PAT")
            fodesaf = line("CR_FODESAF_PAT")
            imas = line("CR_IMAS_PAT")
            ina = line("CR_INA_PAT")
            fcl = line("CR_FCL_PAT")
            rop = line("CR_ROP_PAT")
            rows.append([
                slip.employee_id.identification_id or "",
                slip.employee_id.name or "",
                slip.cr_gross_total,
                sem_emp, ivm_emp, bp_emp, sem_emp + ivm_emp + bp_emp,
                sem_pat, ivm_pat, bp_pat, fodesaf, imas, ina, fcl, rop,
                sem_pat + ivm_pat + bp_pat + fodesaf + imas + ina + fcl + rop,
            ])
        return self._cr_csv_attachment("Reporte_CCSS_%s.csv" % (self.name or self.id), headers, rows)

    def action_cr_download_ins(self):
        self.ensure_one()
        headers = [
            "Identificación", "Empleado", "Puesto", "Salario reportable",
            "Días trabajados", "Horas trabajadas", "Incapacidad INS (días)",
            "Incapacidad INS (horas)",
        ]
        rows = []
        for slip in self._cr_export_slips():
            rows.append([
                slip.employee_id.identification_id or "",
                slip.employee_id.name or "",
                slip.employee_id.job_id.name or "",
                slip.cr_gross_total,
                slip._cr_worked_days(["WORK100", "WORK", "ATTENDANCE"]),
                slip._cr_worked_hours(["WORK100", "WORK", "ATTENDANCE"]),
                slip._cr_worked_days("CR_SICK_INS"),
                slip._cr_worked_hours("CR_SICK_INS"),
            ])
        return self._cr_csv_attachment("Reporte_INS_%s.csv" % (self.name or self.id), headers, rows)
