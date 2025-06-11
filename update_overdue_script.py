#!/usr/bin/env python3
"""
This script manually updates all payment plan lines to recalculate 
overdue days and interest. Run it from the Odoo shell.

Usage:
- Start Odoo shell: odoo-bin shell -c /etc/odoo/odoo.conf -d your_database
- Execute: exec(open('/opt/odoo/odoo_payment_plan/update_overdue_script.py').read())
"""

import logging
from datetime import datetime
from odoo import fields

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)

def update_all_payment_lines():
    """Update all payment plan lines to recalculate overdue days and interest"""
    env = env  # This works in Odoo shell where env is predefined
    
    # Get the current date
    today = fields.Date.context_today(env.user)
    _logger.info(f"Starting overdue payment plans update on {today}")
    
    # Get all unpaid payment plan lines
    lines = env['payment.plan.line'].search([
        ('paid', '=', False),
    ])
    
    _logger.info(f"Found {len(lines)} unpaid payment plan lines")
    
    # Update each line
    updated_count = 0
    for line in lines:
        if not line.date:
            continue
            
        try:
            # Calculate overdue days
            if line.date < today:
                delta = today - line.date
                overdue_days = delta.days
                
                # Calculate interest
                annual_rate = line.payment_plan_id.interest_rate / 100.0 if line.payment_plan_id.interest_rate else 0.10
                daily_rate = annual_rate / 365.0
                interest_amount = line.amount * overdue_days * daily_rate
                total_with_interest = line.amount + interest_amount
                
                # Update values directly
                line.write({
                    'overdue_days': overdue_days,
                    'interest_amount': interest_amount,
                    'total_with_interest': total_with_interest
                })
                updated_count += 1
            else:
                # Reset values for non-overdue lines
                line.write({
                    'overdue_days': 0,
                    'interest_amount': 0, 
                    'total_with_interest': line.amount
                })
        except Exception as e:
            _logger.error(f"Error updating line {line.id}: {str(e)}")
    
    # Commit changes
    env.cr.commit()
    _logger.info(f"Successfully updated {updated_count} overdue payment plan lines")
    
    return f"Updated {updated_count} overdue payment plan lines"

# Execute the function
result = update_all_payment_lines()
print(result)
