"""Backfill the new company-currency fields on existing reconciliations.

Before this version every payment plan lived in the company currency (GTQ), so
the allocated ``amount`` was simultaneously the plan-currency amount and the
company-currency amount, at an implicit exchange rate of 1.

The new multi-currency support splits those into ``amount`` (plan currency) and
``amount_company`` (company currency), bridged by ``exchange_rate``. For every
row that predates the change we set:

    exchange_rate  = 1
    amount_company = amount

which is exact for the single-currency history and leaves those plans behaving
identically to before.
"""


def migrate(cr, version):
    if not version:
        return

    # exchange_rate: default to 1 wherever it was not populated yet.
    cr.execute(
        """
        UPDATE payment_plan_reconciliation
        SET exchange_rate = 1.0
        WHERE exchange_rate IS NULL OR exchange_rate = 0.0
        """
    )

    # amount_company: mirror the allocated amount (rate = 1) where missing.
    cr.execute(
        """
        UPDATE payment_plan_reconciliation
        SET amount_company = amount
        WHERE amount_company IS NULL
        """
    )
