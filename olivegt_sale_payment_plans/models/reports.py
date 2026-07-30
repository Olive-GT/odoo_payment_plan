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
    
    report_type = fields.Selection([
        ('installments_overdue', 'Global de Cuotas por Cobrar')
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

    # Caracteres que Excel no admite en el nombre de una pestaña
    _INVALID_SHEET_CHARS = str.maketrans('', '', '[]:*?/\\\'')

    def _sheet_name(self, base, used, suffix=''):
        """Nombre de pestaña valido, de 31 caracteres como maximo y unico.

        Excel rechaza el libro entero si dos pestañas se llaman igual, y dos
        clientes con nombres largos que empiezan igual colisionan al truncar.
        El sufijo de moneda nunca se recorta: se le quita espacio al nombre,
        porque una pestaña que pierde el "(USD)" deja de decir lo unico que la
        distingue de su gemela.
        """
        clean = (base or 'Cliente').translate(self._INVALID_SHEET_CHARS).strip() or 'Cliente'
        limite = 31 - len(suffix)
        name = f"{clean[:limite].strip()}{suffix}"
        n = 2
        while name.lower() in used:
            tail = f"_{n}{suffix}"
            name = f"{clean[:31 - len(tail)].strip()}{tail}"
            n += 1
        used.add(name.lower())
        return name

    def _generate_installments_overdue(self, workbook):
        """ REPORTE 1: Cuotas por cobrar.

        Una pestaña por cliente y moneda. Separarlas por moneda no es un
        detalle estetico: un cliente puede tener un plan en quetzales y otro en
        dolares, y sumarlos en una misma columna daria un total falso.
        """
        state_mapping = {
            'pending': 'Pendiente', 'partial': 'Parcialmente Asignado',
            'allocated': 'Asignado', 'paid': 'Pagado', 'overdue': 'Vencido',
        }

        title_format = workbook.add_format({'size': 12, 'bold': True, 'align': 'center', 'valign': 'vcenter'})
        subtitle_format = workbook.add_format({'size': 9, 'align': 'center', 'valign': 'vcenter', 'font_color': '#555555'})
        header_format = workbook.add_format({'size': 10, 'bold': True, 'align': 'center', 'valign': 'vcenter', 'bottom': 1, 'top': 1, 'text_wrap': True})
        data_format = workbook.add_format({'size': 10, 'align': 'left', 'valign': 'vcenter'})
        center_format = workbook.add_format({'size': 10, 'align': 'center', 'valign': 'vcenter'})
        section_format = workbook.add_format({'size': 10, 'bold': True, 'align': 'left', 'valign': 'vcenter', 'bg_color': '#EFEFEF'})
        overdue_days_format = workbook.add_format({'size': 10, 'align': 'center', 'valign': 'vcenter', 'font_color': '#B30000'})

        hoy = fields.Date.context_today(self)

        lines = self.env['payment.plan.line'].sudo().search([
            ('payment_plan_id.company_id', '=', self.env.company.id),
            ('state', 'in', ['pending', 'partial', 'overdue']),
            ('paid', '=', False),
        ], order='date asc')

        # Agrupamos por cliente y moneda: son las dos dimensiones que no se
        # pueden mezclar en una misma hoja sin producir totales sin sentido.
        grupos = {}
        for line in lines:
            pendiente = (line.total_with_interest or line.amount or 0.0) - (line.allocated_amount or 0.0)
            rounding = line.currency_id.rounding or 0.01
            if pendiente <= rounding / 2:
                continue
            partner = line.payment_plan_id.partner_id
            grupos.setdefault((partner, line.currency_id), []).append((line, pendiente))

        if not grupos:
            raise UserError("No se encontraron cuotas pendientes de pago en el sistema.")

        # Formato numerico con el simbolo de cada moneda, para que ninguna
        # cifra quede sin identificar al copiarse fuera del reporte
        money_formats = {}

        def money(currency, **extra):
            symbol = (currency.symbol or '').replace('"', '')
            key = (symbol, tuple(sorted(extra.items())))
            if key not in money_formats:
                spec = {'size': 10, 'align': 'right', 'valign': 'vcenter',
                        'num_format': f'"{symbol}" #,##0.00' if symbol else '#,##0.00'}
                spec.update(extra)
                money_formats[key] = workbook.add_format(spec)
            return money_formats[key]

        orden = sorted(
            grupos.items(),
            key=lambda kv: ((kv[0][0].display_name or '').lower(), kv[0][1].name or '')
        )

        resumen = []
        used_names = set()
        resumen_sheet = workbook.add_worksheet('Resumen')
        resumen_sheet.hide_gridlines(0)

        for (partner, currency), registros in orden:
            vencidas = [(l, p) for l, p in registros if l.date and l.date < hoy]
            por_vencer = [(l, p) for l, p in registros if not (l.date and l.date < hoy)]
            filas = vencidas + por_vencer

            etiqueta_moneda = currency.name or ''
            base = partner.name or f"Cliente_{partner.id}"
            # Solo se etiqueta la moneda cuando el cliente tiene mas de una,
            # que es cuando la pestaña necesita distinguirse
            multi_moneda = any(k[0] == partner and k[1] != currency for k in grupos)
            sheet_name = self._sheet_name(
                base, used_names, f" ({etiqueta_moneda})" if multi_moneda else ''
            )

            worksheet = workbook.add_worksheet(sheet_name)
            worksheet.set_landscape()
            worksheet.hide_gridlines(0)

            worksheet.merge_range('A1:K1', (partner.name or '').upper(), title_format)
            worksheet.merge_range('A2:K2',
                                  f"Cuotas pendientes de pago en {etiqueta_moneda} — al {hoy.strftime('%d/%m/%Y')}",
                                  subtitle_format)
            worksheet.set_row(0, 26)

            headers = ['#', 'Plan', 'Descripcion', 'Vence', 'Monto', 'Interes',
                       'Total', 'Aplicado', 'Pendiente', 'Dias mora', 'Estado']
            worksheet.set_row(3, 24)
            for col, header in enumerate(headers):
                worksheet.write(3, col, header, header_format)

            worksheet.set_column('A:A', 5)
            worksheet.set_column('B:B', 22)
            worksheet.set_column('C:C', 30)
            worksheet.set_column('D:D', 12)
            worksheet.set_column('E:I', 14)
            worksheet.set_column('J:J', 10)
            worksheet.set_column('K:K', 20)
            worksheet.freeze_panes(4, 0)

            row = 4
            idx = 0
            total_vencido = 0.0
            total_por_vencer = 0.0

            for etiqueta, bloque in (('VENCIDAS', vencidas), ('POR VENCER', por_vencer)):
                if not bloque:
                    continue
                worksheet.merge_range(row, 0, row, 10, etiqueta, section_format)
                row += 1
                inicio = row

                for line, pendiente in bloque:
                    idx += 1
                    dias = line.overdue_days or 0
                    if not dias and line.date and line.date < hoy:
                        dias = (hoy - line.date).days

                    worksheet.write(row, 0, idx, center_format)
                    worksheet.write(row, 1, line.payment_plan_id.name or '', data_format)
                    worksheet.write(row, 2, line.name or '', data_format)
                    worksheet.write(row, 3, line.date.strftime('%d/%m/%Y') if line.date else '—', center_format)
                    worksheet.write(row, 4, line.amount or 0.0, money(currency))
                    worksheet.write(row, 5, line.interest_amount or 0.0, money(currency))
                    worksheet.write(row, 6, line.total_with_interest or line.amount or 0.0, money(currency))
                    worksheet.write(row, 7, line.allocated_amount or 0.0, money(currency))
                    worksheet.write(row, 8, pendiente, money(currency))
                    worksheet.write(row, 9, dias, overdue_days_format if dias else center_format)
                    worksheet.write(row, 10, state_mapping.get(line.state, line.state or '—'), center_format)
                    row += 1

                subtotal = sum(p for _, p in bloque)
                if etiqueta == 'VENCIDAS':
                    total_vencido = subtotal
                else:
                    total_por_vencer = subtotal

                worksheet.write(row, 3, f"Subtotal {etiqueta.lower()}:",
                                workbook.add_format({'size': 10, 'align': 'right', 'valign': 'vcenter', 'top': 1}))
                for col, letra in ((4, 'E'), (5, 'F'), (6, 'G'), (7, 'H'), (8, 'I')):
                    worksheet.write_formula(row, col, f"=SUM({letra}{inicio + 1}:{letra}{row})",
                                            money(currency, top=1))
                row += 2

            worksheet.write(row, 3, "TOTAL PENDIENTE:",
                            workbook.add_format({'size': 11, 'bold': True, 'align': 'right', 'valign': 'vcenter', 'top': 1}))
            worksheet.write(row, 8, total_vencido + total_por_vencer,
                            money(currency, bold=True, top=1, bottom=2, size=11))

            resumen.append({
                'partner': partner.name or '',
                'currency': etiqueta_moneda,
                'sheet': sheet_name,
                'vencido': total_vencido,
                'por_vencer': total_por_vencer,
                'total': total_vencido + total_por_vencer,
                'cuotas': len(filas),
                'currency_rec': currency,
            })

        # --- Hoja resumen: la cartera de un vistazo, sin sumar entre monedas ---
        resumen_sheet.merge_range('A1:F1', 'CUOTAS PENDIENTES DE PAGO', title_format)
        resumen_sheet.merge_range('A2:F2', f"Al {hoy.strftime('%d/%m/%Y')}", subtitle_format)
        resumen_sheet.set_row(0, 26)
        for col, header in enumerate(['Cliente', 'Moneda', 'Cuotas', 'Vencido', 'Por vencer', 'Total pendiente']):
            resumen_sheet.write(3, col, header, header_format)
        resumen_sheet.set_column('A:A', 38)
        resumen_sheet.set_column('B:B', 10)
        resumen_sheet.set_column('C:C', 9)
        resumen_sheet.set_column('D:F', 16)
        resumen_sheet.freeze_panes(4, 0)

        row = 4
        for item in sorted(resumen, key=lambda r: (-r['vencido'], r['partner'].lower())):
            currency = item['currency_rec']
            resumen_sheet.write(row, 0, item['partner'], data_format)
            resumen_sheet.write(row, 1, item['currency'], center_format)
            resumen_sheet.write(row, 2, item['cuotas'], center_format)
            resumen_sheet.write(row, 3, item['vencido'], money(currency))
            resumen_sheet.write(row, 4, item['por_vencer'], money(currency))
            resumen_sheet.write(row, 5, item['total'], money(currency))
            row += 1

        # Un total por moneda: sumar entre monedas distintas seria un dato falso
        row += 1
        totales = {}
        for item in resumen:
            acc = totales.setdefault(item['currency_rec'], {'vencido': 0.0, 'por_vencer': 0.0, 'total': 0.0})
            acc['vencido'] += item['vencido']
            acc['por_vencer'] += item['por_vencer']
            acc['total'] += item['total']

        for currency, acc in sorted(totales.items(), key=lambda kv: kv[0].name or ''):
            resumen_sheet.write(row, 0, f"TOTAL {currency.name or ''}",
                                workbook.add_format({'size': 10, 'bold': True, 'align': 'left', 'valign': 'vcenter', 'top': 1}))
            resumen_sheet.write(row, 3, acc['vencido'], money(currency, bold=True, top=1))
            resumen_sheet.write(row, 4, acc['por_vencer'], money(currency, bold=True, top=1))
            resumen_sheet.write(row, 5, acc['total'], money(currency, bold=True, top=1, bottom=2))
            row += 1

        return "Cuentas_Por_Cobrar"