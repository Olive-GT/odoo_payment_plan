# Sale Payment Plans

This module extends the Sales Management application in Odoo 18 to add the ability to create payment plans for sales orders.

## Features

- Create payment plans from sale orders
- Multiple payment plans per sale order
- Manual or automatic payment schedule calculation
- Payment plan states (draft, posted, canceled)
- Track payments against payment plans
- Print payment plan reports

## Usage

### Creating a Payment Plan

1. Create a sale order
2. Click on the "Create Payment Plan" button
3. Fill in the payment plan details or use the payment plan calculator

### Payment Plan Calculator

The payment plan calculator allows you to easily create scheduled payments:

- **Initial Payment**: Optional initial payment (e.g., down payment)
- **Regular Installments**: Distribute the remaining amount in equal installments
- **Final Payment**: Optional final payment (e.g., balloon payment)

### Managing Payment Plans

Payment plans go through different states:

- **Draft**: Initial state, plans can be modified
- **Posted**: Payment plan is active and can't be modified
- **Canceled**: Payment plan is canceled

### Tracking Payments

Each payment line can be marked as paid or unpaid:

- Mark specific installments as paid
- Track payment dates and references
- Monitor overall payment progress

## Technical Information

This module depends on:

- `sale_management`: Odoo's sales management module
- `account`: For financial tracking

## Installation

Install this module as you would any other Odoo module.

## License

This module is licensed under the LGPL-3 license.
