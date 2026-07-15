# Costa Rica HR Payroll para Odoo 18 — v5 nativa

Localización de nómina costarricense integrada en los modelos y menús estándar de Odoo 18 Enterprise.

## Integración nativa

- Tipos y estructuras en Nómina > Configuración.
- Reglas salariales en las estructuras estándar.
- Feriados en Ausencias > Configuración > Días festivos (`resource.calendar.leaves`).
- Vacaciones, incapacidades y permisos como tipos nativos de ausencia vinculados a entradas de trabajo.
- SEM, IVM, Banco Popular y cada carga patronal como reglas salariales separadas y visibles.
- Tramos de renta, tasas y vigencias como parámetros auxiliares, sin duplicar el motor de nómina.

## Actualización desde v4

La rutina nativa migra feriados del modelo legado al modelo estándar de Odoo y desactiva las reglas agregadas de cargas sociales para evitar rebajos duplicados.

Antes de producción deben realizarse planillas paralelas y confirmar políticas de incapacidad, INS, embargos, pensiones y cuentas contables.
