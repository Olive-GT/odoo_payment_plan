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
    
    # NUEVO CAMPO: Define el tipo técnico del reporte
    report_type = fields.Selection([
        ('installments_overdue', 'Global de Cuotas por Cobrar'),
        ('payment_history', 'Historial de Pagos Recibidos'),  # Ejemplo de reporte 2
        ('interest_generated', 'Reporte de Intereses Clientes'), # Ejemplo de reporte 3
    ], string="Tipo de Reporte", required=True, default='installments_overdue')

    excel_file = fields.Binary(string="Archivo Excel")
    excel_filename = fields.Char(string="Nombre del Archivo")

    def action_descargar_reporte(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError("La librería 'xlsxwriter' no está instalada en el servidor.")

        # MAPEO DE REPORTES ---
        # Vincula el valor de 'report_type' con la función correspondiente
        report_methods = {
            'installments_overdue': self._generate_installments_overdue
        }

        method = report_methods.get(self.report_type)
        if not method:
            raise UserError(f"El reporte tipo '{self.report_type}' no tiene una función asignada.")

        # 1. Crear el buffer de memoria común
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # 2. Ejecutar la función específica del reporte inyectándole el workbook
        filename_prefix = method(workbook)

        # 3. Finalizar el empaquetado común
        workbook.close()
        output.seek(0)
        excel_data = base64.b64encode(output.read())
        output.close()

        # Guardar y retornar la acción de descarga
        today_str = fields.Date.today().strftime('%d_%m_%Y')
        self.write({
            'excel_file': excel_data,
            'excel_filename': f"{filename_prefix}_{today_str}.xlsx"
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=excel_file&download=true&filename={self.excel_filename}',
            'target': 'self',
        }

    def _generate_installments_overdue(self, workbook):
        """ REPORTE 1: Cuotas por cobrar (Tu código actual estructurado) """
        # Creamos los formatos locales que requiere este reporte específico
        title_format = workbook.add_format({'size': 10, 'align': 'center', 'valign': 'vcenter'})
        header_format = workbook.add_format({'size': 10, 'align': 'center', 'valign': 'vcenter', 'bottom': 1, 'top': 1})
        data_format = workbook.add_format({'size': 10, 'align': 'left', 'valign': 'vcenter'})
        center_format = workbook.add_format({'size': 10, 'align': 'center', 'valign': 'vcenter'})
        amount_format = workbook.add_format({'size': 10, 'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0.00'})
        total_label_format = workbook.add_format({'size': 10, 'align': 'right', 'valign': 'vcenter', 'top': 1})
        total_amount_format = workbook.add_format({'size': 10, 'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0.00', 'top': 1, 'bottom': 2})

        all_lines = self.env['payment.plan.line'].sudo().search([
            ('state', 'in', ['pending', 'partial', 'overdue']),
            ('paid', '=', False),
            ('date', '<', fields.Date.context_today(self))
        ])
        
        if not all_lines:
            raise UserError("No se encontraron cuotas vencidas y pendientes en el sistema.")

        partners = all_lines.mapped('payment_plan_id.partner_id')
        sorted_partners = sorted(partners, key=lambda p: p.display_name or '')

        for partner in sorted_partners:
            p_lines_sorted = self.env['payment.plan.line'].sudo().search([
                ('payment_plan_id.partner_id', '=', partner.id),
                ('state', 'in', ['pending', 'partial', 'overdue']),
                ('paid', '=', False),
                ('date', '<', fields.Date.context_today(self))
            ], order='date asc')

            if not p_lines_sorted:
                continue

            raw_name = partner.name or f"Cliente_{partner.id}"
            sheet_name = raw_name[:30].translate(str.maketrans('', '', '[]:*?\/'))
            worksheet = workbook.add_worksheet(sheet_name)
            worksheet.set_landscape()
            worksheet.hide_gridlines(0)

            # --- Armado de Tabla ---
            worksheet.merge_range('A1:I1', partner.name.upper(), title_format)
            worksheet.set_row(0, 30)

            headers = ['number', 'payment_plan', 'description', 'overdue_date', 'total_amount', 'allocated_amount', 'pending_amount', 'overdue_days', 'state']
            worksheet.set_row(1, 22) 
            for col_num, header in enumerate(headers):
                worksheet.write(1, col_num, header, header_format)
            
            worksheet.set_column('A:A', 5)
            worksheet.set_column('B:B', 22)
            worksheet.set_column('C:C', 30)
            worksheet.set_column('D:D', 13)
            worksheet.set_column('E:G', 15)
            worksheet.set_column('H:H', 12)
            worksheet.set_column('I:I', 15)

            state_mapping = {
                'pending': 'Pendiente', 'partial': 'Parcialmente Asignado',
                'allocated': 'Asignado', 'paid': 'Pagado', 'overdue': 'Vencido'
            }

            row_idx = 3
            for idx, line in enumerate(p_lines_sorted):
                worksheet.set_row(row_idx, 18)
                worksheet.write(row_idx, 0, idx + 1, center_format)
                worksheet.write(row_idx, 1, line.payment_plan_id.name or '', data_format)
                worksheet.write(row_idx, 2, line.name or '', data_format)
                
                date_str = line.date.strftime('%d/%m/%Y') if line.date else '—'
                worksheet.write(row_idx, 3, date_str, center_format)
                
                worksheet.write(row_idx, 4, line.amount or 0.0, amount_format)
                worksheet.write(row_idx, 5, line.allocated_amount or 0.0, amount_format)
                
                pending_amount = (line.amount or 0.0) - (line.allocated_amount or 0.0)
                worksheet.write(row_idx, 6, pending_amount, amount_format)

                # overdue days 
                temp_overdue_days = 0
                if line.overdue_days:
                    temp_overdue_days = line.overdue_days
                # calculo de los dias de vencimiento calculado segun el overdue_date
                elif line.date:
                    hoy = fields.Date.context_today(self)
                    if line.date < hoy:
                        temp_overdue_days = (hoy - line.date).days

                worksheet.write(row_idx, 7, temp_overdue_days, center_format)


                readable_state = state_mapping.get(line.state, line.state or '—')
                worksheet.write(row_idx, 8, readable_state, center_format)
                row_idx += 1

            worksheet.set_row(row_idx, 20)
            worksheet.write(row_idx, 3, "Total Cliente:", total_label_format)
            worksheet.write_formula(row_idx, 4, f"=SUM(E4:E{row_idx})", total_amount_format)
            worksheet.write_formula(row_idx, 5, f"=SUM(F4:F{row_idx})", total_amount_format)
            worksheet.write_formula(row_idx, 6, f"=SUM(G4:G{row_idx})", total_amount_format)

        return "Cuentas_Por_Cobrar"