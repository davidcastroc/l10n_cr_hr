# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)
MODULE = "l10n_cr_hr"


class CrPayrollNativeSetup(models.AbstractModel):
    _name = "cr.payroll.native.setup"
    _description = "Configuración nativa de Nómina Costa Rica"

    @api.model
    def setup_native_payroll(self):
        self._setup_structure_type()
        self._setup_structure_rules()
        self._setup_input_availability()
        self._remove_legacy_aggregate_rules()
        self._setup_native_menus()
        return True

    def _ref(self, name):
        xmlid = name if "." in name else f"{MODULE}.{name}"
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _setup_structure_type(self):
        structure_type = self._ref("structure_type_cr")
        if not structure_type:
            return

        structures = self.env["hr.payroll.structure"].sudo().browse([
            record.id for record in (
                self._ref("structure_monthly"),
                self._ref("structure_biweekly"),
                self._ref("structure_weekly"),
                self._ref("structure_hourly"),
                self._ref("structure_extraordinary"),
                self._ref("structure_aguinaldo"),
                self._ref("structure_settlement"),
            ) if record
        ])
        if structures:
            values = {"type_id": structure_type.id}
            if "use_worked_day_lines" in structures._fields:
                values["use_worked_day_lines"] = True
            structures.write(values)

        default_structure = self._ref("structure_biweekly")
        if default_structure and "default_struct_id" in structure_type._fields:
            structure_type.default_struct_id = default_structure

    @staticmethod
    def _is_cr_rule(rule):
        return (rule.name or "").startswith("CR -")

    def _cleanup_structure(self, structure, allowed_codes, base_rule=None):
        """Elimina de una estructura CR reglas estándar/legadas que duplican cálculos.

        No toca reglas de otras estructuras ni reglas globales. Las reglas propias de
        Costa Rica se reconocen por su nombre y por el registro base específico.
        """
        if not structure:
            return
        keep_ids = {base_rule.id} if base_rule else set()
        for rule in structure.rule_ids:
            keep = rule.id in keep_ids or (
                self._is_cr_rule(rule) and rule.code in allowed_codes
            )
            if not keep:
                rule.unlink()

    def _copy_rule_to_structure(self, source_rule, structure):
        matches = structure.rule_ids.filtered(
            lambda rec: rec.code == source_rule.code and self._is_cr_rule(rec)
        )
        if len(matches) > 1:
            matches[1:].unlink()
            matches = matches[:1]
        values = {
            "name": source_rule.name,
            "sequence": source_rule.sequence,
            "category_id": source_rule.category_id.id,
            "condition_select": source_rule.condition_select,
            "amount_select": source_rule.amount_select,
            "amount_python_compute": source_rule.amount_python_compute,
            "appears_on_payslip": source_rule.appears_on_payslip,
            "active": source_rule.active,
        }
        if matches:
            matches.write(values)
        else:
            source_rule.copy({**values, "struct_id": structure.id})

    def _setup_structure_rules(self):
        monthly = self._ref("structure_monthly")
        biweekly = self._ref("structure_biweekly")
        weekly = self._ref("structure_weekly")
        hourly = self._ref("structure_hourly")
        if not monthly:
            return

        bases = {
            monthly: self._ref("rule_basic"),
            biweekly: self._ref("rule_basic_biweekly"),
            weekly: self._ref("rule_basic_weekly"),
            hourly: self._ref("rule_basic_hourly"),
        }
        common_codes = {
            "CR_UNPAID_TIME", "CR_VACATION_PAY", "CR_DISABILITY_PAY",
            "CR_COMMISSION", "CR_BONUS", "CR_AVAILABILITY", "CR_RETROACTIVE",
            "CR_OTHER_INCOME", "CR_OT_15", "CR_OT_20", "CR_OT_30",
            "CR_REIMBURSEMENT", "GROSS", "CR_SEM_EMP", "CR_IVM_EMP",
            "CR_BP_EMP", "CR_RENTA", "CR_RECUR_DED", "CR_OTHER_DED",
            "NET", "CR_SEM_PAT", "CR_IVM_PAT", "CR_BP_PAT",
            "CR_FODESAF_PAT", "CR_IMAS_PAT", "CR_INA_PAT", "CR_FCL_PAT",
            "CR_ROP_PAT", "CR_PROV_AGUINALDO", "CR_PROV_VACATION",
        }

        # Primero limpia mensual y toma solo las reglas CR como plantilla.
        self._cleanup_structure(monthly, common_codes | {"BASIC"}, bases[monthly])
        source_rules = monthly.rule_ids.filtered(
            lambda rule: self._is_cr_rule(rule) and rule.code in common_codes
        ).sorted(key=lambda rule: rule.sequence)

        for target in (biweekly, weekly, hourly):
            if not target:
                continue
            self._cleanup_structure(target, common_codes | {"BASIC"}, bases[target])
            for source_rule in source_rules:
                self._copy_rule_to_structure(source_rule, target)

        # Las estructuras especiales se mantienen deliberadamente pequeñas.
        special_specs = {
            self._ref("structure_extraordinary"): {
                "GROSS", "CR_SEM_EMP", "CR_IVM_EMP", "CR_BP_EMP",
                "CR_RENTA", "CR_RECUR_DED", "CR_OTHER_DED", "NET",
            },
            self._ref("structure_aguinaldo"): {"CR_AGUINALDO", "NET"},
            self._ref("structure_settlement"): {"GROSS", "CR_RECUR_DED", "NET"},
        }
        for structure, allowed_codes in special_specs.items():
            if not structure:
                continue
            unwanted = structure.rule_ids.filtered(
                lambda rule: not (self._is_cr_rule(rule) and rule.code in allowed_codes)
            )
            if unwanted:
                unwanted.unlink()

    def _setup_input_availability(self):
        input_model = self.env["hr.payslip.input.type"].sudo()
        if "struct_ids" not in input_model._fields:
            return

        regular = [
            self._ref("structure_monthly"), self._ref("structure_biweekly"),
            self._ref("structure_weekly"), self._ref("structure_hourly"),
        ]
        extraordinary = self._ref("structure_extraordinary")
        aguinaldo = self._ref("structure_aguinaldo")
        settlement = self._ref("structure_settlement")
        regular_ids = [record.id for record in regular if record]

        settlement_codes = {
            "CR_SETTLEMENT_SALARY", "CR_SETTLEMENT_VACATION",
            "CR_NOTICE", "CR_SEVERANCE",
        }
        extraordinary_codes = {
            "CR_COMMISSION", "CR_BONUS", "CR_INCENTIVE", "CR_PRODUCTIVITY",
            "CR_AVAILABILITY", "CR_RETROACTIVE", "CR_SALARY_DIFF",
            "CR_OTHER_INCOME", "CR_VIATIC_TAXABLE", "CR_REIMBURSEMENT",
            "CR_OTHER_DED",
        }
        for input_type in input_model.search([("code", "like", "CR_%")]):
            if input_type.code in settlement_codes:
                structure_ids = [settlement.id] if settlement else []
            elif input_type.code == "CR_AGUINALDO_ADJ":
                structure_ids = [record.id for record in (aguinaldo, settlement) if record]
            elif input_type.code in extraordinary_codes:
                structure_ids = regular_ids + ([extraordinary.id] if extraordinary else [])
            else:
                structure_ids = regular_ids
            input_type.write({"struct_ids": [(6, 0, structure_ids)]})

    def _remove_legacy_aggregate_rules(self):
        for name in ("rule_social_employee", "rule_employer_social", "rule_extra_social"):
            rule = self._ref(name)
            if rule:
                rule.unlink()

    def _payroll_menus(self):
        records = self.env["ir.model.data"].sudo().search([
            ("module", "=", "hr_payroll"), ("model", "=", "ir.ui.menu"),
        ])
        result = []
        for imd in records:
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
            score = sum(10 for token in tokens if token in xml_name)
            score += sum(3 for token in tokens if token in source_name)
            if score:
                scored.append((score, -menu.sequence, menu))
        return max(scored, default=(0, 0, False))[2]

    def _setup_native_menus(self):
        candidates = self._payroll_menus()
        if not candidates:
            return
        payroll_root = self._pick_menu(candidates, ("root", "payroll"))
        config_menu = self._pick_menu(
            candidates, ("configuration", "config", "settings"), require_parent=True
        )
        payslip_menu = self._pick_menu(candidates, ("payslip", "slip"), require_parent=True)

        config_root = self._ref("menu_cr_configuration_root")
        incidents = self._ref("menu_cr_incidents")
        terminations = self._ref("menu_cr_terminations")
        if config_root:
            config_root.parent_id = config_menu or payroll_root
        operations_parent = payslip_menu or payroll_root or config_root
        if incidents and operations_parent:
            incidents.parent_id = operations_parent
        if terminations and operations_parent:
            terminations.parent_id = operations_parent
