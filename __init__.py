from . import models
from . import wizard

def post_init_hook(env):
    """Completa estructuras y ubica el menú CR bajo Configuración de Nómina si existe."""
    # Odoo Enterprise puede cambiar el XML ID del menú de configuración entre revisiones.
    # El menú se carga inicialmente sin padre para evitar bloquear la instalación.
    menu = env.ref("l10n_cr_hr_payroll.menu_cr_payroll_root", raise_if_not_found=False)
    parent = False
    for xmlid in (
        "hr_payroll.menu_hr_payroll_configuration",
        "hr_payroll.menu_hr_payroll_config",
        "hr_payroll.menu_hr_payroll_configuration_root",
    ):
        parent = env.ref(xmlid, raise_if_not_found=False)
        if parent:
            break
    if menu and parent:
        menu.parent_id = parent

    monthly = env.ref("l10n_cr_hr_payroll.structure_monthly")
    targets = [
        env.ref("l10n_cr_hr_payroll.structure_biweekly"),
        env.ref("l10n_cr_hr_payroll.structure_weekly"),
        env.ref("l10n_cr_hr_payroll.structure_hourly"),
    ]
    skip = {"BASIC"}
    for target in targets:
        for rule in monthly.rule_ids.filtered(lambda r: r.code not in skip):
            if not target.rule_ids.filtered(lambda r: r.code == rule.code):
                rule.copy({"struct_id": target.id, "name": rule.name})
