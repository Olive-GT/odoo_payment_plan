{
    'name': 'Sale Payment Plans',
    'version': '18.0.1.0.0',
    'summary': 'Payment Plans for Sale Orders',
    'description': """
        This module allows you to create payment plans from sale orders.
        Features:
        - Create payment plans from sale orders
        - Multiple payment plans per sale order
        - Manual or automatic payment schedule calculation
        - Payment plan states (draft, posted, canceled)
    """,
    'category': 'Sales',
    'author': 'Olive GT',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'base',
        'mail',
        'sale_management',
    ],'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/payment_plan_sequence.xml',
        'data/payment_plan_cron.xml',
        'reports/payment_plan_report.xml',
        'views/payment_plan_line_views.xml',
        'views/payment_plan_reconciliation_views.xml',
        'views/payment_plan_view.xml',
        'views/menu_payment_plan.xml',
        'views/sale_order_views.xml',
        'wizards/payment_plan_calculator_views.xml',
        'wizards/payment_plan_reconciliation_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}
