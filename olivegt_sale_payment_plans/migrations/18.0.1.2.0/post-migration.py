"""Fijar el remitente del recibo en la compania del registro.

Hasta esta version la plantilla del recibo no definia ``email_from``. El
composer de Odoo entonces lo resolvia con el correo del **autor**, es decir el
usuario que aprieta el boton (mail_compose_message.py, _compute_email_from):

    if composer.template_id.email_from:
        composer._set_value_from_template('email_from')
    ...
    else:
        composer.email_from = self.env.user.email_formatted

El efecto era que los recibos salian firmados por quien los enviaba y no por la
compania duena del plan: 67 recibos de DESARROLLO CINCO quedaron marcados con la
direccion de la contadora de PALE. Ese dominio es ademas lo que enruta al
servidor SMTP via ``from_filter``, asi que el remitente equivocado tambien
elegia la cuenta de correo equivocada.

El campo se agrega tambien al XML para instalaciones nuevas, pero el registro
existente vive en un bloque ``noupdate="1"``: ``_load_records`` omite todo
registro cuyo ir_model_data.noupdate sea verdadero durante un upgrade, y el
``ON CONFLICT`` de ``_build_update_xmlids_query`` nunca reescribe esa columna.
Sin esta migracion el cambio del XML no llegaria jamas a las bases ya
instaladas.

Solo se toca la plantilla si sigue sin remitente, para no pisar una
personalizacion hecha desde la interfaz.
"""


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        UPDATE mail_template t
           SET email_from = '{{ object.company_id.email_formatted or user.email_formatted }}'
          FROM ir_model_data d
         WHERE d.module = 'olivegt_sale_payment_plans'
           AND d.name = 'mail_template_payment_plan_reconciliation_receipt'
           AND d.model = 'mail.template'
           AND t.id = d.res_id
           AND COALESCE(t.email_from, '') = ''
        """
    )
