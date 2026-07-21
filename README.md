# Localización de Nómina Costa Rica para Odoo 18 Enterprise

Versión **18.0.3.0.0**. Extiende la nómina nativa de Odoo 18; no crea una segunda nómina.

Incluye estructuras mensual, quincenal, semanal, por horas, extraordinaria, aguinaldo y liquidación; ingresos variables; rebajos por tiempo no laborado; horas extra 1.5, doble y triple; CCSS y cargas patronales parametrizadas por vigencia; renta progresiva 2026 acumulada por mes; feriados; vacaciones; incapacidades configurables; deducciones con saldo; incidencias aprobables; aguinaldo legal y asistente de liquidación.

## Importante
Los ejemplos antiguos aportaron escenarios, no valores legales. Esta versión evita duplicados y centraliza las tasas por vigencia. Debe instalarse primero en staging y validarse con tres planillas reales. Las reglas de incapacidad permanecen desactivadas hasta confirmar el tratamiento de eTribu y la póliza INS.

## Convención de inputs
Los inputs `CR_OT_15`, `CR_OT_20`, `CR_OT_30`, `CR_UNPAID_HOURS`, `CR_UNPAID_DAYS` y `CR_TARDINESS` reciben **cantidades** (horas o días). Los demás inputs reciben montos monetarios.
