# -*- coding: utf-8 -*-

from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class HrPayslipEmployees(models.TransientModel):
    _inherit = "hr.payslip.employees"

    cr_run_id = fields.Many2one(
        "hr.payslip.run",
        string="Lote CR",
        default=lambda self: self._cr_default_run(),
        readonly=True,
    )

    cr_process_type = fields.Selection(
        related="cr_run_id.cr_process_type",
        string="Tipo de proceso CR",
        readonly=True,
    )

    cr_allowed_structure_ids = fields.Many2many(
        "hr.payroll.structure",
        compute="_compute_cr_allowed_structure_ids",
        string="Estructuras permitidas CR",
    )

    cr_allowed_employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_cr_allowed_employee_ids",
        string="Empleados permitidos CR",
    )

    @api.model
    def _cr_default_run(self):
        context = self.env.context
        run_id = (
            context.get("cr_payslip_run_id")
            or context.get("default_payslip_run_id")
            or context.get("payslip_run_id")
        )

        if not run_id and context.get("active_model") == "hr.payslip.run":
            run_id = context.get("active_id")

        if not run_id:
            return self.env["hr.payslip.run"]

        return self.env["hr.payslip.run"].browse(run_id).exists()

    def _cr_get_run(self):
        self.ensure_one()
        return self.cr_run_id or self._cr_default_run()

    @api.depends("cr_process_type")
    def _compute_cr_allowed_structure_ids(self):
        Structure = self.env["hr.payroll.structure"]

        for wizard in self:
            process = wizard.cr_process_type or "ordinary"

            if process == "ordinary":
                wizard.cr_allowed_structure_ids = Structure.search([
                    ("cr_is_regular_payroll", "=", True),
                    (
                        "cr_structure_usage",
                        "in",
                        ["monthly", "biweekly", "weekly", "hourly"],
                    ),
                ])
                continue

            xmlid_by_process = {
                "aguinaldo": "l10n_cr_hr.structure_aguinaldo",
                "extraordinary": "l10n_cr_hr.structure_extraordinary",
                "settlement": "l10n_cr_hr.structure_settlement",
            }

            xmlid = xmlid_by_process.get(process)

            if not xmlid:
                wizard.cr_allowed_structure_ids = Structure
                continue

            structure = self.env.ref(
                xmlid,
                raise_if_not_found=False,
            )

            wizard.cr_allowed_structure_ids = (
                structure if structure else Structure
            )

    def _cr_approved_pending_terminations(self):
        self.ensure_one()

        run = self._cr_get_run()

        if not run:
            return self.env["cr.payroll.termination"]

        domain = [
            ("state", "=", "approved"),
            ("payslip_id", "=", False),
        ]

        if run.date_end:
            domain.append(
                ("termination_date", "<=", run.date_end)
            )

        if run.company_id:
            domain.append(
                ("company_id", "=", run.company_id.id)
            )

        return self.env["cr.payroll.termination"].search(
            domain,
            order="termination_date asc, employee_id asc",
        )

    @api.depends(
        "cr_process_type",
        "structure_id",
        "department_id",
        "job_id",
        "cr_run_id",
    )
    def _compute_cr_allowed_employee_ids(self):
        Employee = self.env["hr.employee"]
        Contract = self.env["hr.contract"]

        for wizard in self:
            process = wizard.cr_process_type or "ordinary"

            if process == "settlement":
                wizard.cr_allowed_employee_ids = (
                    wizard
                    ._cr_approved_pending_terminations()
                    .mapped("employee_id")
                )
                continue

            if process in ("aguinaldo", "extraordinary"):
                contracts = Contract.search([
                    ("state", "=", "open"),
                ])

                wizard.cr_allowed_employee_ids = (
                    contracts.mapped("employee_id")
                )
                continue

            if not wizard.structure_id:
                wizard.cr_allowed_employee_ids = Employee
                continue

            contracts = Contract.search([
                ("state", "=", "open"),
                (
                    "cr_payroll_structure_id",
                    "=",
                    wizard.structure_id.id,
                ),
            ])

            wizard.cr_allowed_employee_ids = (
                contracts.mapped("employee_id")
            )

    @api.model
    def get_view(
        self,
        view_id=None,
        view_type="form",
        **options
    ):
        result = super().get_view(
            view_id=view_id,
            view_type=view_type,
            **options,
        )

        if view_type != "form":
            return result

        arch = etree.fromstring(
            result["arch"].encode("utf-8")
            if isinstance(result["arch"], str)
            else result["arch"]
        )

        forms = arch.xpath("//form")

        if arch.tag == "form":
            form = arch
        elif forms:
            form = forms[0]
        else:
            form = arch

        cr_fields = (
            "cr_run_id",
            "cr_process_type",
            "cr_allowed_structure_ids",
            "cr_allowed_employee_ids",
        )

        # Odoo 18: los campos agregados dinámicamente al XML también deben
        # registrarse en la metadata "models" que recibe OWL. Si no se hace,
        # el frontend encuentra el nodo <field/> pero reporta "field is undefined".
        models_meta = dict(result.get("models", {}))
        current_fields = models_meta.get("hr.payslip.employees", ())

        if isinstance(current_fields, tuple):
            models_meta["hr.payslip.employees"] = (
                current_fields
                + tuple(
                    field_name
                    for field_name in cr_fields
                    if field_name not in current_fields
                )
            )
        elif isinstance(current_fields, list):
            for field_name in cr_fields:
                if field_name not in current_fields:
                    current_fields.append(field_name)
        elif isinstance(current_fields, set):
            current_fields.update(cr_fields)
        elif not current_fields:
            models_meta["hr.payslip.employees"] = tuple(cr_fields)

        result["models"] = models_meta

        existing = {
            node.get("name")
            for node in form.xpath(".//field")
            if node.get("name")
        }

        for field_name in cr_fields:
            if field_name not in existing:
                node = etree.Element("field")
                node.set("name", field_name)
                node.set("invisible", "1")
                form.insert(0, node)

        for node in arch.xpath(
            "//field[@name='structure_id']"
        ):
            node.set(
                "domain",
                "[('id', 'in', cr_allowed_structure_ids)]",
            )
            node.set(
                "readonly",
                "cr_process_type and cr_process_type != 'ordinary'",
            )
            node.set(
                "options",
                "{'no_create': True, 'no_open': True}",
            )

        for node in arch.xpath(
            "//field[@name='employee_ids']"
        ):
            node.set(
                "domain",
                "[('id', 'in', cr_allowed_employee_ids)]",
            )

        result["arch"] = etree.tostring(
            arch,
            encoding="unicode",
        )

        return result



    def get_employees_domain(self):
        """
        Extiende el dominio nativo de Odoo sin reemplazar su mecanismo
        de cómputo del wizard.

        Esto es importante porque `structure_id` es un campo computed,
        store=True y readonly=False en Odoo 18. Si reemplazamos
        `_compute_employee_ids` u onchanges del campo, el cliente puede
        terminar recalculando y limpiando la estructura seleccionada.
        """
        domain = super().get_employees_domain()

        process = self.cr_process_type or "ordinary"
        self._compute_cr_allowed_employee_ids()
        allowed = self.cr_allowed_employee_ids

        if process == "ordinary":
            if self.structure_id:
                domain = domain + [
                    ("id", "in", allowed.ids),
                ]
            return domain

        if process in ("aguinaldo", "extraordinary", "settlement"):
            domain = domain + [
                ("id", "in", allowed.ids),
            ]

        return domain


    def compute_sheet(self):
        for wizard in self:
            process = wizard.cr_process_type or "ordinary"

            wizard._compute_cr_allowed_structure_ids()
            wizard._compute_cr_allowed_employee_ids()

            if process != "ordinary":
                required = (
                    wizard.cr_allowed_structure_ids[:1]
                )

                if not required:
                    raise UserError(
                        _(
                            "No existe una estructura salarial "
                            "configurada para este tipo de proceso."
                        )
                    )

                wizard.structure_id = required

            if process == "settlement":
                pending = (
                    wizard
                    ._cr_approved_pending_terminations()
                )

                if not pending:
                    raise ValidationError(
                        _(
                            "No existen liquidaciones aprobadas "
                            "pendientes de procesar para este lote."
                        )
                    )

                valid_employees = pending.mapped(
                    "employee_id"
                )

                invalid = (
                    wizard.employee_ids
                    - valid_employees
                )

                if invalid:
                    raise ValidationError(
                        _(
                            "Solo pueden incluirse empleados con "
                            "una liquidación aprobada y todavía "
                            "sin recibo:\n%s"
                        )
                        % "\n".join(
                            invalid.mapped("name")
                        )
                    )

            if process == "ordinary":
                if not wizard.structure_id:
                    raise ValidationError(
                        _(
                            "Debe seleccionar una estructura "
                            "salarial ordinaria."
                        )
                    )

                invalid = wizard.employee_ids.filtered(
                    lambda employee:
                        employee.contract_id
                        and employee.contract_id.cr_payroll_structure_id
                        and employee.contract_id.cr_payroll_structure_id
                        != wizard.structure_id
                )

                if invalid:
                    raise ValidationError(
                        _(
                            "Los siguientes empleados no "
                            "pertenecen a la estructura "
                            "seleccionada:\n%s"
                        )
                        % "\n".join(
                            invalid.mapped("name")
                        )
                    )

        return super().compute_sheet()
