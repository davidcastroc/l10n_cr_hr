# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class CrPayrollNativeSetup(models.AbstractModel):
    _name = "cr.payroll.native.setup"
    _description = "Configuración nativa de Nómina Costa Rica"

    @api.model
    def setup_native_payroll(self):
        """Integra la localización dentro de los menús y modelos nativos de Odoo.

        Se ejecuta desde XML tanto en instalación como en actualización. No depende
        de un XML ID específico del menú de Configuración de Enterprise, ya que ese
        identificador ha cambiado entre revisiones de Odoo 18.
        """
        self._setup_structure_type()
        self._setup_structure_rules()
        self._setup_input_availability()
        self._setup_social_rules()
        self._migrate_public_holidays_to_native()
        self._setup_native_menus()
        return True

    def _ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _setup_structure_type(self):
        main_type = self._ref("l10n_cr_hr_payroll.structure_type_cr")
        if not main_type:
            return

        structures = self.env["hr.payroll.structure"].sudo().browse([
            record.id
            for record in (
                self._ref("l10n_cr_hr_payroll.structure_monthly"),
                self._ref("l10n_cr_hr_payroll.structure_biweekly"),
                self._ref("l10n_cr_hr_payroll.structure_weekly"),
                self._ref("l10n_cr_hr_payroll.structure_hourly"),
                self._ref("l10n_cr_hr_payroll.structure_extraordinary"),
                self._ref("l10n_cr_hr_payroll.structure_aguinaldo"),
                self._ref("l10n_cr_hr_payroll.structure_settlement"),
            )
            if record
        ])
        if structures:
            structures.write({"type_id": main_type.id})
            if "use_worked_day_lines" in structures._fields:
                structures.write({"use_worked_day_lines": True})

        default_structure = self._ref("l10n_cr_hr_payroll.structure_biweekly")
        if default_structure and "default_struct_id" in main_type._fields:
            main_type.default_struct_id = default_structure

        # Migra instalaciones 3.x que creaban cuatro tipos distintos.
        legacy_xmlids = (
            "structure_type_monthly",
            "structure_type_biweekly",
            "structure_type_weekly",
            "structure_type_hourly",
        )
        imd_model = self.env["ir.model.data"].sudo()
        contract_model = self.env["hr.contract"].sudo()
        for legacy_name in legacy_xmlids:
            imd = imd_model.search([
                ("module", "=", "l10n_cr_hr_payroll"),
                ("name", "=", legacy_name),
                ("model", "=", "hr.payroll.structure.type"),
            ], limit=1)
            legacy = self.env["hr.payroll.structure.type"].sudo().browse(imd.res_id).exists() if imd else False
            if not legacy or legacy == main_type:
                continue
            if "structure_type_id" in contract_model._fields:
                contract_model.search([("structure_type_id", "=", legacy.id)]).write({"structure_type_id": main_type.id})
            self.env["hr.payroll.structure"].sudo().search([("type_id", "=", legacy.id)]).write({"type_id": main_type.id})
            try:
                legacy.unlink()
                imd.unlink()
            except Exception:
                _logger.warning("No fue posible eliminar el tipo de estructura legado %s", legacy.display_name, exc_info=True)
                if "active" in legacy._fields:
                    legacy.active = False

    def _setup_structure_rules(self):
        monthly = self._ref("l10n_cr_hr_payroll.structure_monthly")
        if not monthly:
            return
        target_xmlids = (
            "l10n_cr_hr_payroll.structure_biweekly",
            "l10n_cr_hr_payroll.structure_weekly",
            "l10n_cr_hr_payroll.structure_hourly",
        )
        # Cada estructura conserva su regla BASIC específica; el resto se replica
        # de forma controlada y sin duplicar códigos.
        common_rules = monthly.rule_ids.filtered(lambda rule: rule.code != "BASIC")
        for xmlid in target_xmlids:
            target = self._ref(xmlid)
            if not target:
                continue
            existing_codes = set(target.rule_ids.mapped("code"))
            for rule in common_rules:
                if rule.code not in existing_codes:
                    rule.copy({"struct_id": target.id})
                    existing_codes.add(rule.code)

    def _setup_input_availability(self):
        input_model = self.env["hr.payslip.input.type"].sudo()
        if "struct_ids" not in input_model._fields:
            return

        regular_structures = [
            self._ref("l10n_cr_hr_payroll.structure_monthly"),
            self._ref("l10n_cr_hr_payroll.structure_biweekly"),
            self._ref("l10n_cr_hr_payroll.structure_weekly"),
            self._ref("l10n_cr_hr_payroll.structure_hourly"),
            self._ref("l10n_cr_hr_payroll.structure_extraordinary"),
        ]
        regular_structures = [record.id for record in regular_structures if record]
        aguinaldo = self._ref("l10n_cr_hr_payroll.structure_aguinaldo")
        settlement = self._ref("l10n_cr_hr_payroll.structure_settlement")

        settlement_codes = {"CR_SETTLEMENT_SALARY", "CR_SETTLEMENT_VACATION", "CR_NOTICE", "CR_SEVERANCE"}
        aguinaldo_codes = {"CR_AGUINALDO_ADJ"}
        inputs = input_model.search([("code", "like", "CR_%")])
        for input_type in inputs:
            if input_type.code in settlement_codes:
                ids = [settlement.id] if settlement else []
            elif input_type.code in aguinaldo_codes:
                ids = [record.id for record in (aguinaldo, settlement) if record]
            else:
                ids = regular_structures
            input_type.write({"struct_ids": [(6, 0, ids)]})


    def _setup_social_rules(self):
        # Las reglas agregadas de versiones anteriores se desactivan para evitar
        # duplicar rebajos/cargas. Las reglas individuales quedan visibles en la
        # estructura salarial nativa.
        for xmlid in (
            "l10n_cr_hr_payroll.rule_social_employee",
            "l10n_cr_hr_payroll.rule_employer_social",
            "l10n_cr_hr_payroll.rule_extra_social",
        ):
            rule = self._ref(xmlid)
            if rule and "active" in rule._fields:
                rule.active = False

    def _migrate_public_holidays_to_native(self):
        if "cr.payroll.public.holiday" not in self.env:
            return
        Legacy = self.env["cr.payroll.public.holiday"].sudo()
        Native = self.env["resource.calendar.leaves"].sudo()
        from datetime import datetime, time, timedelta
        from odoo import fields
        for legacy in Legacy.search([]):
            start = datetime.combine(legacy.date, time.min)
            end = start + timedelta(days=1)
            domain = [("cr_is_public_holiday", "=", True), ("date_from", "=", fields.Datetime.to_string(start))]
            if not Native.search_count(domain):
                Native.create({
                    "name": "CR - %s" % legacy.name,
                    "date_from": fields.Datetime.to_string(start),
                    "date_to": fields.Datetime.to_string(end),
                    "company_id": legacy.company_id.id or self.env.company.id,
                    "cr_is_public_holiday": True,
                    "cr_mandatory_pay": legacy.mandatory_pay,
                    "cr_holiday_type": legacy.holiday_type,
                    "cr_legal_source": legacy.source,
                })

    def _payroll_menus(self):
        imd_records = self.env["ir.model.data"].sudo().search([
            ("module", "=", "hr_payroll"),
            ("model", "=", "ir.ui.menu"),
        ])
        result = []
        for imd in imd_records:
            menu = self.env["ir.ui.menu"].sudo().browse(imd.res_id).exists()
            if menu:
                result.append((imd.name.lower(), menu))
        return result

    @staticmethod
    def _pick_menu(candidates, tokens, require_parent=False):
        scored = []
        for xml_name, menu in candidates:
            if require_parent and not menu.parent_id:
                continue
            source_name = (menu.name or "").lower()
            score = sum(10 for token in tokens if token in xml_name) + sum(3 for token in tokens if token in source_name)
            if score:
                scored.append((score, -menu.sequence, menu))
        return max(scored, default=(0, 0, False))[2]

    def _setup_native_menus(self):
        candidates = self._payroll_menus()
        if not candidates:
            _logger.warning("No se encontraron menús nativos de hr_payroll para integrar Nómina Costa Rica")
            return

        payroll_root = self._pick_menu(candidates, ("root", "payroll"))
        config_menu = self._pick_menu(candidates, ("configuration", "config", "settings"), require_parent=True)
        payslip_menu = self._pick_menu(candidates, ("payslip", "slip"), require_parent=True)

        config_root = self._ref("l10n_cr_hr_payroll.menu_cr_configuration_root")
        incident_menu = self._ref("l10n_cr_hr_payroll.menu_cr_incidents")
        termination_menu = self._ref("l10n_cr_hr_payroll.menu_cr_terminations")

        if config_root:
            config_root.parent_id = config_menu or payroll_root
            config_root.sequence = 95
        operations_parent = payslip_menu or payroll_root or config_root
        if incident_menu and operations_parent:
            incident_menu.parent_id = operations_parent
            incident_menu.sequence = 85
        if termination_menu and operations_parent:
            termination_menu.parent_id = operations_parent
            termination_menu.sequence = 90
