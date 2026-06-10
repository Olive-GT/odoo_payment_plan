from odoo import models, fields, api
from odoo.exceptions import UserError
import base64

class Reporte(models.Model):
    _name = 'olivegt_sale_payment_plans.reporte_installments'
    _description = 'Reportes de Cuestas por cobrar'

    name = fields.Char(string='Nombre', required=True)
    description = fields.Text(string='Descripción')
    
    # Archivo a descargar
    report_file = fields.Binary(string='Archivo de Reporte')
    file_name = fields.Char(string='Nombre del Archivo')

    def action_descargar_reporte(self):
        self.ensure_one()
        
        if not self.report_file:
            raise UserError('Este reporte aún no tiene un archivo disponible para descargar.')

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model=olivegt_sale_payment_plans.reporte&id={self.id}&field=report_file&filename_field=file_name&download=true',
            'target': 'self',
        }
