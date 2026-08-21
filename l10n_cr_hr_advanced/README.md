# RH Costa Rica - Nómina Avanzada 18.0.5.0.0

Módulo complementario genérico para Odoo 18 + `l10n_cr_hr`.

## Principios de esta versión

### No contiene parámetros de un cliente específico
Este módulo no utiliza porcentajes, montos, topes o resultados definidos por un UAT particular.
Las obligaciones legales se delegan al motor principal de Nómina Costa Rica y a sus modelos
parametrizados por vigencia y compañía:

- `cr.payroll.legal.parameter`
- `cr.payroll.social.contribution`
- `cr.payroll.tax.bracket`
- `cr.payroll.disability.rule`
- reglas salariales y contratos de Odoo

### Administrador
Los usuarios normales mantienen segregación entre preparación y aprobación.
Un usuario con el grupo técnico **Administrador / Ajustes** (`base.group_system`) puede
preparar y aprobar el mismo proceso. La autoaprobación queda registrada expresamente.

Esto aplica a:
- retroactivos;
- eventos tardíos;
- correcciones de marcación;
- acuerdos de liquidación.

### Retroactivos
El módulo calcula únicamente diferencias de conceptos del período origen.
Las reglas salariales pueden configurarse mediante **Políticas de recálculo retroactivo**:

- Excluir.
- Recalcular proporcionalmente al salario.
- Mantener el importe original.

Si no existe una política explícita, solo salario básico y horas extra se consideran
proporcionales de forma segura. Otros conceptos se excluyen hasta ser configurados.

Las cargas sociales, renta, aguinaldo, vacaciones y demás impactos se calculan por el
motor principal al procesar la complementaria; no existen tasas UAT hardcodeadas.

### Incapacidades / eventos tardíos
Los porcentajes patronales, subsidios, rangos de días y vigencias provienen exclusivamente
de `cr.payroll.disability.rule`. Si falta configuración legal para algún día, el proceso
se bloquea en lugar de inventar un porcentaje.

### Liquidación
La referencia legal sigue siendo el resultado del motor `cr.payroll.termination`.
El módulo avanzado no reemplaza los cálculos legales; únicamente:
- congela la referencia;
- permite acuerdos negociados auditados;
- controla horas extra pendientes;
- registra evidencia;
- genera una CxC contable del préstamo residual cuando corresponda.

### Correcciones de marcación
Conserva valores originales, motivo, evidencia, solicitante, aprobador y fecha.
El Administrador puede autoaprobar y queda auditado.

## Importante
Antes de producción, validar las reglas legales y sus vigencias para cada compañía.
La falta de configuración debe corregirse en la parametrización, no en código.
