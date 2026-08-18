# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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


    # -------------------------------------------------------------------------
    # Vacaciones CR - sincronización de saldo inicial con hr_holidays
    # -------------------------------------------------------------------------

    def _cr_get_vacation_leave_type(self):
        """Devuelve el tipo de permiso oficial usado para vacaciones CR.

        Se prioriza la relación con el tipo de entrada de trabajo cuyo código
        de nómina es CR_VACATION. Como respaldo, busca por nombre.
        """
        self.ensure_one()

        LeaveType = self.env["hr.leave.type"].sudo()

        # Búsqueda principal: el tipo de permiso vinculado al work entry type
        # CR - Vacaciones pagadas / CR_VACATION.
        WorkEntryType = self.env["hr.work.entry.type"].sudo()
        work_entry_type = WorkEntryType.search(
            [("code", "=", "CR_VACATION")],
            limit=1,
        )

        leave_type = False
        if work_entry_type:
            leave_type = LeaveType.search(
                [
                    ("work_entry_type_id", "=", work_entry_type.id),
                    "|",
                    ("company_id", "=", self.company_id.id),
                    ("company_id", "=", False),
                ],
                limit=1,
            )

        # Respaldo para instalaciones donde el vínculo no esté disponible.
        if not leave_type:
            leave_type = LeaveType.search(
                [
                    ("name", "=", "CR - Vacaciones"),
                    "|",
                    ("company_id", "=", self.company_id.id),
                    ("company_id", "=", False),
                ],
                limit=1,
            )

        return leave_type

    def _cr_opening_vacation_allocation_name(self):
        """Nombre técnico estable para evitar asignaciones duplicadas."""
        self.ensure_one()
        return "CR - Saldo inicial vacaciones [EMP-%s]" % self.id

    def _cr_sync_opening_vacation_allocation(self):
        """Sincroniza el saldo inicial migrado con Vacaciones nativo de Odoo.

        El campo ``cr_vacation_opening_days`` conserva el dato histórico
        importado, mientras que ``hr.leave.allocation`` es la fuente operativa
        que Odoo usa para determinar cuántos días puede solicitar el empleado.

        La operación es idempotente:
        - no crea duplicados;
        - si ya existe una asignación aprobada con el mismo monto, no hace nada;
        - si existe una asignación pendiente, la actualiza y aprueba;
        - si una asignación aprobada tiene otro monto, se bloquea la modificación
          automática para no alterar saldos ya consumidos sin revisión.
        """
        Allocation = self.env["hr.leave.allocation"].sudo()

        for employee in self:
            opening_days = max(employee.cr_vacation_opening_days or 0.0, 0.0)

            # Un saldo cero no requiere asignación.
            if not opening_days:
                continue

            leave_type = employee._cr_get_vacation_leave_type()
            if not leave_type:
                raise ValidationError(
                    _(
                        "No se encontró el tipo de permiso 'CR - Vacaciones' "
                        "vinculado al tipo de entrada de trabajo CR_VACATION."
                    )
                )

            allocation_name = employee._cr_opening_vacation_allocation_name()

            allocation = Allocation.search(
                [
                    ("employee_id", "=", employee.id),
                    ("holiday_status_id", "=", leave_type.id),
                    ("name", "=", allocation_name),
                ],
                limit=1,
            )

            vals = {
                "name": allocation_name,
                "employee_id": employee.id,
                "holiday_status_id": leave_type.id,
                "allocation_type": "regular",
                "number_of_days": opening_days,
                "date_from": (
                    employee.cr_vacation_opening_date
                    or fields.Date.context_today(employee)
                ),
            }

            if not allocation:
                allocation = Allocation.create(vals)
            elif allocation.state in ("validate", "validate1"):
                # Ya está aprobada. Si el valor coincide, la sincronización
                # ya fue realizada correctamente.
                if abs((allocation.number_of_days or 0.0) - opening_days) < 0.00001:
                    continue

                raise ValidationError(
                    _(
                        "La asignación inicial de vacaciones de %(employee)s "
                        "ya está aprobada por %(allocated).2f días, pero el "
                        "saldo inicial del empleado indica %(opening).2f días. "
                        "Revise la asignación antes de modificar el saldo "
                        "histórico para evitar alterar vacaciones ya utilizadas."
                    )
                    % {
                        "employee": employee.name,
                        "allocated": allocation.number_of_days,
                        "opening": opening_days,
                    }
                )
            else:
                allocation.write(vals)

            # El saldo debe quedar aprobado para aparecer como disponible en
            # Gestión -> Vacaciones.
            if allocation.state not in ("validate", "validate1"):
                allocation.action_validate()

        return True

    def action_cr_sync_opening_vacations(self):
        """Acción pública para sincronización manual/masiva."""
        self._cr_sync_opening_vacation_allocation()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)

        # Si el saldo inicial se carga durante la creación y hr_holidays ya
        # está configurado, sincronizamos automáticamente.
        to_sync = employees.filtered(lambda e: e.cr_vacation_opening_days > 0)
        if to_sync:
            to_sync._cr_sync_opening_vacation_allocation()

        return employees

    def write(self, vals):
        result = super().write(vals)

        # Importaciones o correcciones de saldo inicial deben reflejarse en
        # Vacaciones nativo sin requerir una segunda carga manual.
        if {
            "cr_vacation_opening_days",
            "cr_vacation_opening_date",
        } & set(vals):
            self.filtered(
                lambda e: e.cr_vacation_opening_days > 0
            )._cr_sync_opening_vacation_allocation()

        return result

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
