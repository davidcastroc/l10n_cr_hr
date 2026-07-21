# Cambios 18.0.3.0.2

Esta entrega parte exactamente del módulo `l10n_cr_hr_payroll` suministrado por el cliente.

## Cambios funcionales

- No se cambió el nombre técnico del módulo.
- No se separó ninguna funcionalidad en otro módulo.
- Se conservaron modelos, vistas, menús, XML IDs, categorías, estructuras y reglas existentes.
- Se verificó que `cr.payroll.termination` contiene los campos `include_notice` e `include_severance` usados por la vista de liquidación.
- Se conservó el `post_init_hook` existente que replica las reglas comunes de la estructura mensual hacia quincenal, semanal y por horas, excluyendo únicamente `BASIC`, porque cada frecuencia posee su propia regla base.

## Cambio de versión

- `18.0.3.0.1` → `18.0.3.0.2`.

## Validación estática

- XML bien formado.
- Python compila correctamente.
- Referencias de campos de la vista de liquidación presentes en el modelo.
- Estructuras y reglas base conservadas.
