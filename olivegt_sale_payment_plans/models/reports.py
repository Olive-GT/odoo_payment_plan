import io
import base64
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
        
        # 2. Buscar las cuotas directamente usando el modelo real de Odoo
        # NOTA: Reemplaza 'sale.payment.plan.line' por el nombre técnico real de tu modelo de cuotas
        lines = self.env['sale.payment.plan.line'].search([
            ('state', 'in', ['pending', 'partial', 'overdue'])
        ])
        
        if not lines:
            raise UserError("No se encontraron cuotas pendientes o vencidas en el sistema para generar el reporte.")

        # Agrupar las cuotas por cliente (partner_id)
        partner_lines = {}
        for line in lines:
            partner = line.partner_id
            if not partner:
                continue
            if partner not in partner_lines:
                partner_lines[partner] = []
            partner_lines[partner].append(line)

        # 3. Construir una pestaña (Sheet) por cada Cliente
        # Ordenamos los clientes alfabéticamente por su nombre visible
        sorted_partners = sorted(partner_lines.keys(), key=lambda p: p.display_name or '')

        for partner in sorted_partners:
            p_lines = partner_lines[partner]
            # Ordenar las cuotas de este cliente por fecha de vencimiento
            p_lines_sorted = sorted(p_lines, key=lambda l: l.due_date or fields.Date.today())

            # Sanitizar el nombre de la pestaña (Máximo 31 caracteres, sin caracteres prohibidos por Excel)
            raw_name = partner.name or f"Cliente_{partner.id}"
            sheet_name = raw_name[:30].translate(str.maketrans('', '', '[]:*?\/'))
            
            worksheet = workbook.add_worksheet(sheet_name)
            worksheet.set_landscape() # Formato horizontal para que quepa bien

            # Forzar cuadrícula visible en Excel
            worksheet.hide_gridlines(0)

            # Título superior de la hoja
            worksheet.merge_range('A1:I1', f"CUOTAS POR COBRAR - {partner.name.upper()}", title_format)
            worksheet.set_row(0, 30)

            # Definir encabezados de columnas
            headers = ['#', 'Plan', 'Cuota', 'Vence', 'Original', 'Pagado', 'Pendiente', 'Días Venc.', 'Estado']
            worksheet.set_row(2, 22) # Altura del encabezado
            for col_num, header in enumerate(headers):
                worksheet.write(2, col_num, header, header_format)
            
            # Anchos óptimos de columna
            worksheet.set_column('A:A', 5)   # #
            worksheet.set_column('B:B', 22)  # Plan
            worksheet.set_column('C:C', 30)  # Cuota (Descripción)
            worksheet.set_column('D:D', 13)  # Vence
            worksheet.set_column('E:G', 15)  # Original, Pagado, Pendiente
            worksheet.set_column('H:H', 12)  # Días Venc.
            worksheet.set_column('I:I', 13)  # Estado

            # Mapeo amigable para los estados técnicos
            state_mapping = {
                'pending': 'Pendiente',
                'partial': 'Parcial',
                'overdue': 'Vencido'
            }

            # Llenar las filas de la tabla
            row_idx = 3
            for idx, line in enumerate(p_lines_sorted):
                worksheet.set_row(row_idx, 18)
                worksheet.write(row_idx, 0, idx + 1, center_format)
                worksheet.write(row_idx, 1, line.payment_plan_id.name or '', data_format)
                worksheet.write(row_idx, 2, line.description or '', data_format)
                
                date_str = line.due_date.strftime('%d/%m/%Y') if line.due_date else '—'
                worksheet.write(row_idx, 3, date_str, center_format)
                
                worksheet.write(row_idx, 4, line.original_amount or 0.0, amount_format)
                worksheet.write(row_idx, 5, line.allocated_amount or 0.0, amount_format)
                worksheet.write(row_idx, 6, line.pending_amount or 0.0, amount_format)
                worksheet.write(row_idx, 7, line.overdue_days or 0, center_format)
                
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

        # Guardar el archivo generado en el registro actual
        self.write({
            'excel_file': excel_data,
            'excel_filename': f"Cuentas_Por_Cobrar_{fields.Date.today().strftime('%d_%m_%Y')}.xlsx"
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=excel_file&download=true&filename={self.excel_filename}',
            'target': 'self',
        }