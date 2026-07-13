# Plan de implementación: Planes de pago en dólares

**Principio rector (innegociable):** no lastimar nada de lo que existe hoy. Los planes
en quetzales actuales deben seguir comportándose **idéntico** — misma captura, misma
conciliación, misma impresión. Los dólares se agregan **encima**, como una capacidad
opcional que solo se activa cuando el plan nace de un pedido en USD.

---

## 1. Moneda del plan: RESUELTO (era configuración, no código)

La moneda del plan se hereda del pedido con un campo *related* almacenado:

```python
# models/payment_plan.py
currency_id = fields.Many2one('res.currency', related='sale_id.currency_id', store=True)
```

**Confirmado:** la herencia funciona bien. El síntoma de "se queda en quetzales" era que la
lista de precios en USD no se había guardado en la cotización. Con el pedido correctamente
en USD, el plan hereda USD automáticamente.

> **Conclusión:** NO se toca `currency_id`. La sección 4.1 queda descartada y con ella todo
> el riesgo de afectar planes viejos por recomputar la moneda.

---

## 2. Diseño conceptual

El problema de fondo: hoy el monto de una conciliación (`amount`) se usa para **dos cosas
distintas que hoy son la misma** porque todo es GTQ:

- Cuánto **consume de la cuota** (mundo del cliente / plan).
- Cuánto **consume del depósito bancario** (mundo contable).

Cuando el plan es USD y el depósito es GTQ, estos dos números **se separan**. La solución
es representarlos explícitamente y unirlos con una tasa:

| Concepto | Campo | Moneda | Se valida contra |
|---|---|---|---|
| Consumido de la cuota | `amount` (ya existe) | Moneda del plan (USD) | Monto de la cuota |
| Consumido del depósito | `amount_company` (nuevo) | Compañía (GTQ) | Saldo del `account.move.line` |
| Puente | `exchange_rate` (nuevo) | — | `amount_company = amount × exchange_rate` |

**Cálculo de doble vía** (lo que pediste): fijado el depósito, el usuario pone la **tasa** y
se calcula el **USD**, o pone el **USD a consumir** y se calcula la **tasa**.

**Garantía de no-regresión:** para un plan en GTQ, la moneda del plan = la de la compañía,
entonces `exchange_rate = 1` y `amount_company = amount`. Toda la lógica nueva **degenera
exactamente al comportamiento actual.**

---

## 3. Inventario de puntos afectados (auditoría del código)

Lugares donde hoy `amount` se compara/suma contra `move_line.balance` (GTQ). Estos son los
que deben pasar a usar `amount_company`:

1. `models/payment_plan_reconciliation.py` → `_check_available_amount` (no exceder el depósito).
2. `models/account_move_line.py` → `_compute_payment_plan_available_amount` (saldo disponible / `is_fully_consumed`).
3. `wizards/payment_plan_reconciliation.py` → `PaymentPlanReconciliationWizardLine._compute_available` (suma `amount` de recs por move line).

Lugares que se quedan **igual** (comparan contra la cuota, en moneda del plan):

- `_check_payment_plan_line_amount` (no exceder la cuota).
- `action_confirm` que marca la cuota como pagada (suma `amount` vs total de la cuota).
- Reportes: usan `currency_id.symbol` del plan → un plan USD imprime `$` y el recibo dirá
  "DÓLARES" en letras **automáticamente**.

---

## 4. Cambios concretos, archivo por archivo

### 4.1 `models/payment_plan.py` — moneda del plan

**Sin cambios.** La herencia *related* ya funciona (ver sección 1).

### 4.2 `models/payment_plan_reconciliation.py` — campos y validaciones

Campos nuevos:

```python
company_currency_id = fields.Many2one(related='company_id.currency_id')      # GTQ
amount_company = fields.Monetary(currency_field='company_currency_id')       # GTQ del depósito
exchange_rate  = fields.Float(default=1.0, digits=(12, 6))                    # GTQ por 1 USD
```

- `_check_available_amount`: sumar y comparar `amount_company` contra `abs(move_line.balance)`.
- `_check_payment_plan_line_amount`: **sin cambios** (sigue con `amount` vs cuota).
- `create()`: si no viene `amount_company`, calcularlo como `amount × exchange_rate`
  (con `exchange_rate=1` por defecto → retrocompatible).

### 4.3 `models/account_move_line.py`

- `_compute_payment_plan_available_amount`: sumar `amount_company` (no `amount`) para el
  disponible y `is_fully_consumed`. Con planes GTQ el resultado es idéntico.

### 4.4 `wizards/payment_plan_reconciliation.py` — captura con doble vía

En `PaymentPlanReconciliationWizardLine`:

- Agregar `exchange_rate` y `amount_company` (GTQ del depósito).
- `original_amount`/`available_amount` siguen en GTQ (ya usan `abs(balance)`), sumando
  `amount_company` de las recs existentes.
- `amount` pasa a ser lo consumido de la cuota (USD).
- Onchange de doble vía: `amount = amount_company / exchange_rate` ⇄
  `exchange_rate = amount_company / amount`.

En `action_confirm` del wizard: pasar `amount`, `amount_company` y `exchange_rate` al crear
la `payment.plan.reconciliation`.

### 4.5 Vistas

- `wizards/payment_plan_reconciliation_views.xml`: mostrar tasa y monto en GTQ junto al USD.
- `views/payment_plan_reconciliation_views.xml`: mostrar los campos nuevos en la ficha/lista.
- Cosmético: cambiar la "Q" fija por el símbolo de la moneda en
  `_compute_allocation_summary` y `_compute_move_lines_summary` (para que un plan USD no
  muestre "Q").

### 4.6 Reportes

- Estado de cuenta y recibo: **sin cambios de fondo** (ya usan el símbolo de la moneda del
  plan). Opcional: mostrar como referencia la tasa y el equivalente en GTQ de cada pago.

---

## 5. Migración de datos (crítico para no romper lo existente)

Las conciliaciones actuales no tendrán `amount_company` ni `exchange_rate`. Se agrega un
script de migración del módulo que, para todas las filas existentes:

- `exchange_rate = 1`
- `amount_company = amount`

Como todas las conciliaciones actuales son de planes en GTQ, esto es exacto y deja el
sistema idéntico. Se prueba primero en la copia de staging.

---

## 6. Plan de pruebas (antes de desplegar)

Sobre una **copia de la base de producción**:

1. **No-regresión (lo más importante):** tomar un plan viejo en GTQ y verificar que:
   - Se ve igual (montos, saldos, estados).
   - Concilia igual (disponible del depósito, marcar como pagado).
   - Imprime el estado de cuenta y el recibo **idénticos** a hoy.
2. **Flujo nuevo USD:** crear un plan desde un pedido USD, armar cuotas en dólares,
   conciliar un depósito en GTQ con tasa (probar la doble vía), y verificar que el estado
   de cuenta cuadra en dólares.
3. **Mixto:** confirmar que ambos tipos de plan coexisten sin interferencia.

---

## 7. Orden de implementación (por fases, cada una verificable)

1. **Fase 0 — Diagnóstico** de la moneda (sección 1). Sin código.
2. **Fase 1 — Modelo:** campos nuevos en la conciliación + migración + ajuste de las 3
   validaciones. Verificar no-regresión en GTQ.
3. **Fase 2 — Captura:** doble vía en el wizard + vistas.
4. **Fase 3 — Plan USD:** corrección de moneda (si aplica) + prueba del flujo completo USD.
5. **Fase 4 — Reportes/cosmético** y pruebas finales.

Todo en una **rama aparte**; nada llega a producción hasta pasar la sección 6.

---

## 8. Riesgos y cómo se controlan

| Riesgo | Control |
|---|---|
| Reescribir moneda de planes viejos | No usar compute con `depends`; fijar solo en `create()`. |
| Conciliaciones viejas sin `amount_company` | Migración que rellena `= amount`, `rate = 1`. |
| Cálculo de disponible del depósito se descuadra | Cambiar las 3 sumas a `amount_company`; con GTQ es idéntico. |
| Regresión silenciosa | Prueba de no-regresión (6.1) obligatoria antes de desplegar. |
