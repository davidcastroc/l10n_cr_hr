# RH Costa Rica - Nómina Odoo 18

Versión 18.0.7.0.0.

Correcciones principales:

- El nombre técnico del módulo es `l10n_cr_hr` en todas las referencias XML/Python.
- Limpieza automática de reglas estándar duplicadas dentro de las estructuras CR.
- Sincronización de las reglas comunes entre mensual, quincenal, semanal y por horas.
- Estructuras especiales limitadas a las reglas que les corresponden.
- Eliminación de reglas agregadas antiguas de cargas sociales para evitar doble cálculo.
- Asistente de feriados idempotente: omite cualquier traslape nativo existente.
- Etiquetas personalizadas de incapacidades completamente en español.
- Vista de lotes compatible con `hr_payroll.hr_payslip_run_form` de Odoo 18.
- Icono para la aplicación auxiliar RH Costa Rica.

## Importante

Este módulo debe instalarse y validarse primero en Odoo.sh Staging. Antes de producción se deben ejecutar planillas paralelas y validar políticas del cliente, cuentas contables, incapacidades CCSS/INS, embargos, pensiones, vacaciones, renta y aguinaldo.

El plan legal de vacaciones debe configurarse con la política aprobada del cliente. El mínimo legal general corresponde a dos semanas por cada cincuenta semanas de labores continuas; el día por mes es la regla proporcional mínima en terminación antes de completar ese período.


## Versión 18.0.11.0.0

- Tasas CCSS 2026: SEM trabajador 5,50 %, IVM trabajador 4,33 %, SEM patrono 9,25 %, IVM patrono 5,58 %.
- Banco Popular trabajador en 0 % y patrono en 0,25 %.
- Bases mínimas contributivas 2026: SEM ₡346.789 e IVM ₡324.590.
- Acumulación mensual de cargas sociales y renta para nóminas quincenales/semanales.
- Pago de feriado trabajado: adicional sencillo en mensual/quincenal y doble en semanal.
- Movimientos de deducciones con prevención de doble aplicación y reversión al devolver el recibo a borrador/cancelar.
- Validación de lote antes del cierre.
- Lactancia conectada a ausencias nativas.
