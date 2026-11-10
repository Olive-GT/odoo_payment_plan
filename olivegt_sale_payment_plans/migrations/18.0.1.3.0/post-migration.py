"""Recalcular lo pagado y el saldo de los planes existentes.

Hasta esta version ``amount_paid`` solo sumaba las cuotas marcadas como
pagadas. Un abono parcial aplicado a una cuota (por ejemplo un anticipo al pago
final) aparecia en el detalle de cuotas, pero no en el Total Pagado ni en el
saldo del estado de cuenta y del recibo.

El calculo ahora tambien cuenta lo aplicado a cuotas no pagadas. Como los campos
son almacenados, cambiar el ``@api.depends`` no recalcula los planes que ya
existen; hay que forzarlo aqui.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    plans = env['payment.plan'].with_context(active_test=False).search([])
    env.add_to_compute(plans._fields['amount_paid'], plans)
    env.add_to_compute(plans._fields['amount_residual'], plans)
    plans.flush_recordset(['amount_paid', 'amount_residual'])
