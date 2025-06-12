# Deployment Instructions for Fixed olivegt_sale_payment_plans Module

## Overview of Fixes
1. Fixed indentation issues in Python code
2. Removed unsupported Owl template directives (`t-if`, `t-att-class`, etc.) in XML views
3. Fixed XML structure issues in views
4. Properly escaped XML special characters (replaced `<` with `&lt;` in attributes)

## Deployment Steps

### 1. Upload the Fixed Module

```bash
# Connect to your Odoo server
ssh user@your_odoo_server

# Create a backup of the current module
cd /opt/odoo/odoo_payment_plan/
mv olivegt_sale_payment_plans olivegt_sale_payment_plans_backup_$(date +%Y%m%d)

# Upload the fixed zip file to the server
# (This step will be done using SCP or any file transfer method)
```

### 2. Extract the Fixed Module

```bash
# Extract the uploaded zip file
cd /opt/odoo/odoo_payment_plan/
unzip olivegt_sale_payment_plans_completely_fixed.zip

# Set proper permissions
chown -R odoo:odoo olivegt_sale_payment_plans/
```

### 3. Restart Odoo Service

```bash
# Restart the Odoo service
sudo systemctl restart odoo
```

### 4. Update the Module in Odoo Interface

1. Log in to Odoo with administrator credentials
2. Go to Apps > Update Apps List
3. Search for "Payment Plans" in the Apps list
4. Click on the module and select "Upgrade" or "Update"

### 5. Verify the Module is Working

1. Navigate to Payment Plans menu
2. Check if the views load correctly
3. Create a test payment plan to ensure functionality

## Troubleshooting

If issues persist after deployment:

1. Check Odoo server logs: `/var/log/odoo/odoo-server.log`
2. Temporarily set debugging mode in Odoo config file
3. Check for any remaining Owl template directives in the view files
4. Verify that the report templates are correctly formatted

## Key Files Modified

1. `wizards/payment_plan_allocation_wizard.py` - Fixed indentation
2. `views/payment_allocation_dashboard.xml` - Fixed XML structure
3. `views/payment_plan_views.xml` - Removed Owl directives
4. `reports/payment_plan_report.xml` - Removed unsupported report directives
