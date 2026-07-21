# Ajustes v9 – recibo limpio e integración de ausencias

## Qué hace
- Las reglas variables solo generan línea cuando existe una entrada distinta de cero.
- La categoría `SALARY_ADJ` se muestra como **Deducciones por tiempo no laborado**.
- Vacaciones, permisos, CCSS, INS, maternidad y paternidad tienen tipo de entrada de trabajo nativo.
- El permiso sin goce rebaja automáticamente días u horas generados por Vacaciones.
- Incapacidades y licencias calculan la parte patronal únicamente si existen reglas activas y validadas.

## Importante
Las reglas de incapacidad vienen desactivadas. Deben configurarse y aprobarse antes del go-live.
Las vacaciones pagadas ya están incluidas en el salario fijo; no se agregan otra vez al bruto. `CR_VACATION_PAY` queda disponible solamente para ajustes extraordinarios aprobados.

## Limpieza de datos de prueba
El código no puede corregir entradas de trabajo históricas duplicadas. Para un empleado de prueba:
1. Corregir la fecha de inicio del contrato.
2. Eliminar entradas de trabajo del período incorrecto.
3. Regenerar las entradas del 1 al 15 o del 16 al último día.
4. Crear un recibo nuevo; no reutilizar uno calculado con entradas antiguas.
