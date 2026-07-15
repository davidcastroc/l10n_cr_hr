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

## Versión 18.0.6.0.0

- Aplicación auxiliar renombrada a **RH Costa Rica** con icono propio.
- Dependientes fiscales por empleado para créditos de renta de hijos y cónyuge.
- Saldos iniciales importables de vacaciones y remuneraciones acumuladas para aguinaldo.
- El cálculo de aguinaldo incorpora remuneraciones históricas migradas dentro del período legal.
- Tipo de proceso en lotes: ordinario, aguinaldo, extraordinario o liquidación.
- Deducciones recurrentes visibles desde la ficha del empleado.
- Etiquetas personalizadas en español.
- Sincronización estricta de reglas entre mensual, quincenal, semanal y por horas.
- Limpieza de reglas improcedentes en estructuras extraordinaria, aguinaldo y liquidación.
- Los feriados no se cargan directamente desde XML para evitar traslapes; se generan en el modelo nativo de Vacaciones.
