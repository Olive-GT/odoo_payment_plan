import io
from odoo.fields import Date
from odoo import models, fields, api
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

class ReporteInstallments(models.Model):
    _name = 'olivegt_sale_payment_plans.reporte_installments'
    _description = 'Controlador de Reportes'

    name = fields.Char(string="Title", required=True)
    description = fields.Text(string="Description")
    
    # almacenar temporalmente el Excel generado
    excel_file = fields.Binary(string="Archivo Excel")
    excel_filename = fields.Char(string="Nombre del Archivo")

    def action_descargar_reporte(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError("La librería 'xlsxwriter' no está instalada en el servidor.")

        # 1. Crear el buffer de memoria para el archivo
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        title_format = workbook.add_format({
            'bold': True,
            'size': 14,
            'align': 'center',
            'valign': 'vcenter'
        })

        header_format = workbook.add_format({
            'bold': True,
            'size': 10,
            'align': 'center',
            'valign': 'vcenter',
            'bottom': 1,
            'top': 1,
            'bg_color': '#F2F2F2'  # Gris claro muy sutil típico de Odoo
        })

        data_format = workbook.add_format({
            'size': 10,
            'align': 'left',
            'valign': 'vcenter'
        })

        center_format = workbook.add_format({
            'size': 10,
            'align': 'center',
            'valign': 'vcenter'
        })

        amount_format = workbook.add_format({
            'size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00'
        })

        total_label_format = workbook.add_format({
            'bold': True,
            'size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'top': 1
        })

        total_amount_format = workbook.add_format({
            'bold': True,
            'size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
            'top': 1,
            'bottom': 2  
        })
        
        # 2. Buscar las cuotas directamente usando el modelo real de Odoo
        lines = self.env['payment.plan.line'].sudo().search([
            ('state', 'in', ['pending', 'partial', 'overdue'])
        ])
        
        if not lines:
            raise UserError("No se encontraron cuotas pendientes o vencidas en el sistema para generar el reporte.")

        # Agrupar las cuotas por cliente
        partner_lines = {}
        for line in lines:
            partner = line.sudo().payment_plan_id.partner_id
            if not partner:
                continue 
                
            if partner not in partner_lines:
                partner_lines[partner] = []
            partner_lines[partner].append(line)

        # 3. Construir una pestaña (Sheet) por cada Cliente
        sorted_partners = sorted(partner_lines.keys(), key=lambda p: p.display_name or '')

        for partner in sorted_partners:
            lines = self.env['payment.plan.line'].sudo().search([
                ('state', 'in', ['pending', 'partial', 'overdue']),
                ('paid', '=', False),
                ('date', '<', Date.context_today(self))
            ])
            
            if not lines:
                raise UserError("No se encontraron cuotas vencidas y pendientes en el sistema para generar el reporte.")

            # Sanitizar el nombre de la pestaña
            raw_name = partner.name or f"Cliente_{partner.id}"
            sheet_name = raw_name[:30].translate(str.maketrans('', '', '[]:*?\/'))
            
            worksheet = workbook.add_worksheet(sheet_name)
            worksheet.set_landscape() 

            # Forzar cuadrícula visible en Excel
            worksheet.hide_gridlines(0)

            # Título superior de la hoja
            worksheet.merge_range('A1:I1', f"CUOTAS POR COBRAR - {partner.name.upper()}", title_format)
            worksheet.set_row(0, 30)

            # Definir encabezados de columnas con nombres genéricos limpios tipo reporte Odoo
            headers = ['#', 'Plan de Pago', 'Descripción Cuota', 'Fecha Vence', 'Monto Original', 'Monto Asignado', 'Monto Pendiente', 'Días Venc.', 'Estado']
            worksheet.set_row(2, 22) 
            for col_num, header in enumerate(headers):
                worksheet.write(2, col_num, header, header_format)
            
            # Anchos óptimos de columna
            worksheet.set_column('A:A', 5)   # #
            worksheet.set_column('B:B', 22)  # Plan de Pago
            worksheet.set_column('C:C', 30)  # Descripción Cuota
            worksheet.set_column('D:D', 13)  # Fecha Vence
            worksheet.set_column('E:G', 15)  # Original, Asignado, Pendiente
            worksheet.set_column('H:H', 12)  # Días Venc.
            worksheet.set_column('I:I', 15)  # Estado

            state_mapping = {
                'pending': 'Pendiente',
                'partial': 'Parcialmente Asignado',
                'allocated': 'Asignado',
                'paid': 'Pagado',
                'overdue': 'Vencido'
            }

            # Llenar las filas de la tabla
            row_idx = 3
            for idx, line in enumerate(p_lines_sorted):
                worksheet.set_row(row_idx, 18)
                worksheet.write(row_idx, 0, idx + 1, center_format)
                
                # Nombre del plan de pago (Cabecera)
                worksheet.write(row_idx, 1, line.payment_plan_id.name or '', data_format)
                # Descripción de la línea (Mapeado a tu campo 'name')
                worksheet.write(row_idx, 2, line.name or '', data_format)
                
                # Fecha de vencimiento de la línea
                date_str = line.date.strftime('%d/%m/%Y') if line.date else '—'
                worksheet.write(row_idx, 3, date_str, center_format)
                
                # Montos correctos mapeados a la línea
                worksheet.write(row_idx, 4, line.amount or 0.0, amount_format)
                worksheet.write(row_idx, 5, line.allocated_amount or 0.0, amount_format)
                
                # Cálculo de saldo pendiente correcto por línea individual (Monto original - Monto Asignado)
                pending_amount = (line.amount or 0.0) - (line.allocated_amount or 0.0)
                worksheet.write(row_idx, 6, pending_amount, amount_format)
                
                # Días vencidos de la línea
                worksheet.write(row_idx, 7, line.overdue_days or 0, center_format)
                
                # Estado actual de la línea
                readable_state = state_mapping.get(line.state, line.state or '—')
                worksheet.write(row_idx, 8, readable_state, center_format)
                row_idx += 1

            # Agregar fila de Subtotales por hoja de cliente utilizando fórmulas de Excel nativas
            worksheet.set_row(row_idx, 20)
            worksheet.write(row_idx, 3, "Total Cliente:", total_label_format)
            
            # Excel cuenta las filas desde 1, por lo tanto en las fórmulas usamos row_idx + 1
            worksheet.write_formula(row_idx, 4, f"=SUM(E4:E{row_idx})", total_amount_format)
            worksheet.write_formula(row_idx, 5, f"=SUM(F4:F{row_idx})", total_amount_format)
            worksheet.write_formula(row_idx, 6, f"=SUM(G4:G{row_idx})", total_amount_format)

        # 4. Finalizar el empaquetado del archivo y transformarlo a Base64
        workbook.close()
        output.seek(0)
        excel_data = base64.b64encode(output.read())
        output.close()

        self.write({
            'excel_file': excel_data,
            'excel_filename': f"Cuentas_Por_Cobrar_{fields.Date.today().strftime('%d_%m_%Y')}.xlsx"
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=excel_file&download=true&filename={self.excel_filename}',
            'target': 'self',
        }