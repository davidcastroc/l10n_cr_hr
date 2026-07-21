# -*- coding: utf-8 -*-
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)
MODULE = "l10n_cr_hr_payroll"


class CrPayrollNativeSetup(models.AbstractModel):
    _name = "cr.payroll.native.setup"
    _description = "Configuración nativa de Nómina Costa Rica"

    def _ref(self, name):
        return self.env.ref("%s.%s" % (MODULE, name), raise_if_not_found=False)

    @staticmethod
    def _archive_rules(rules):
        if rules and "active" in rules._fields:
            rules.write({"active": False})

    @api.model
    def setup_native_payroll(self):
        self._setup_structure_rules()
        self._setup_input_availability()
        self._setup_native_menus()
        return True

    def _copy_rule(self, source, structure):
        Rule = self.env["hr.salary.rule"].sudo().with_context(active_test=False)
        matches = Rule.search([("struct_id", "=", structure.id), ("code", "=", source.code)], order="id")
        values = {
            "name": source.name, "code": source.code, "sequence": source.sequence,
            "category_id": source.category_id.id, "condition_select": source.condition_select,
            "condition_python": source.condition_python, "amount_select": source.amount_select,
            "amount_python_compute": source.amount_python_compute,
            "appears_on_payslip": source.appears_on_payslip, "active": True,
            "struct_id": structure.id,
        }
        if matches:
            matches[0].write(values)
            self._archive_rules(matches[1:])
        else:
            Rule.create(values)

    def _setup_structure_rules(self):
        monthly = self._ref("structure_monthly")
        targets = [self._ref("structure_biweekly"), self._ref("structure_weekly"), self._ref("structure_hourly")]
        if not monthly:
            return
        common_codes = {
            "CR_UNPAID_TIME", "CR_VACATION_PAY", "CR_DISABILITY_DED", "CR_DISABILITY_EMP_TAX",
            "CR_DISABILITY_EMP_NONTAX", "CR_DISABILITY_SUBSIDY", "CR_COMMISSION", "CR_BONUS",
            "CR_AVAILABILITY", "CR_RETROACTIVE", "CR_OTHER_INCOME", "CR_OT_15", "CR_OT_20",
            "CR_OT_30", "CR_REIMBURSEMENT", "GROSS", "CR_SEM_EMP", "CR_IVM_EMP", "CR_BP_EMP",
            "CR_RENTA", "CR_RECUR_DED", "CR_OTHER_DED", "NET", "CR_SEM_PAT", "CR_IVM_PAT",
            "CR_BP_PAT", "CR_FODESAF_PAT", "CR_IMAS_PAT", "CR_INA_PAT", "CR_FCL_PAT", "CR_ROP_PAT",
            "CR_AGUINALDO_PROV", "CR_VACATION_PROV", "CR_DISABILITY_AGUINALDO_BASE",
        }
        source_rules = monthly.rule_ids.filtered(lambda rule: rule.active and rule.code in common_codes).sorted(key=lambda rule: (rule.sequence, rule.id))
        for target in targets:
            if not target:
                continue
            for source in source_rules:
                self._copy_rule(source, target)
            rules = self.env["hr.salary.rule"].sudo().with_context(active_test=False).search([("struct_id", "=", target.id)], order="sequence,id")
            seen = set()
            for rule in rules:
                if rule.code == "BASIC" or rule.code in common_codes:
                    if rule.code in seen:
                        self._archive_rules(rule)
                    else:
                        seen.add(rule.code)
                        if not rule.active:
                            rule.active = True
                else:
                    self._archive_rules(rule)
        legacy = self.env["hr.salary.rule"].sudo().with_context(active_test=False).search([("code", "in", ["CR_SOC_EMP", "CR_SOC_PAT", "CR_DISABILITY_PAY"])])
        self._archive_rules(legacy)

    def _setup_input_availability(self):
        Input = self.env["hr.payslip.input.type"].sudo()
        if "struct_ids" not in Input._fields:
            return
        regular = [self._ref("structure_monthly"), self._ref("structure_biweekly"), self._ref("structure_weekly"), self._ref("structure_hourly")]
        extraordinary = self._ref("structure_extraordinary")
        aguinaldo = self._ref("structure_aguinaldo")
        settlement = self._ref("structure_settlement")
        regular_ids = [record.id for record in regular if record]
        settlement_codes = {"CR_SETTLEMENT_SALARY", "CR_SETTLEMENT_VACATION", "CR_NOTICE", "CR_SEVERANCE"}
        for input_type in Input.search([("code", "like", "CR_%")]):
            if input_type.code in settlement_codes:
                ids = [settlement.id] if settlement else []
            elif input_type.code == "CR_AGUINALDO_ADJ":
                ids = [record.id for record in (aguinaldo, settlement) if record]
            else:
                ids = regular_ids + ([extraordinary.id] if extraordinary else [])
            input_type.write({"struct_ids": [(6, 0, ids)]})

    def _setup_native_menus(self):
        root = self._ref("menu_cr_payroll_root")
        if not root:
            return
        for xmlid in ("hr_payroll.menu_hr_payroll_configuration", "hr_payroll.menu_hr_payroll_config", "hr_payroll.menu_hr_payroll_configuration_root"):
            parent = self.env.ref(xmlid, raise_if_not_found=False)
            if parent:
                root.parent_id = parent
                break
