from odoo import models, SUPERUSER_ID, fields
from odoo.exceptions import AccessError


class MailMessage(models.Model):
    _inherit = "mail.message"

    def _original_uid(self):
        """Obtiene el uid real desde el contexto si viene seteado por el flujo de posteo."""
        return self.env.context.get("uid", self.env.uid)

    def _can_modify_chatter(self):
        """Permite editar/eliminar solo a superusuario o al grupo whitelist."""
        uid = self._original_uid()
        if uid == SUPERUSER_ID:
            return True
        user = self.env["res.users"].browse(uid)
        return user.has_group("olivegt_sale_payment_plans.group_chatter_editors")

    def _contains_user_comments(self):
        """True si hay contenido visible al usuario (mensajes o notas), o emails."""
        types = set(self.mapped("message_type"))
        if "comment" in types or "email" in types:
            return True
        # Notas internas como notification+subtype interno
        for msg in self:
            if (
                msg.message_type == "notification"
                and msg.subtype_id
                and getattr(msg.subtype_id, "internal", False)
            ):
                return True
        return False

    def _is_recent_creation_phase(self, threshold_seconds=30):
        """Permite escrituras técnicas inmediatamente tras crear el mensaje."""
        post_flags = (
            "mail_post_autofollow",
            "mail_create_nosubscribe",
            "mail_post_autofollow_partner_ids",
            "default_model",          # común en message_post
            "default_res_id",         # común en message_post
            "mail_post_autofollow_ids",
        )
        if any(self.env.context.get(flag) for flag in post_flags):
            return True
        now = fields.Datetime.now()
        for msg in self:
            if not msg.create_date:
                return False
            if (now - msg.create_date).total_seconds() > threshold_seconds:
                return False
        return True

    def write(self, vals):
        """
        Permitir creación y escrituras técnicas en fase reciente.
        Bloquear edición de contenido visible (body/subject) pasado el umbral,
        salvo superusuario o grupo whitelist.
        """
        if self._contains_user_comments():
            blocked_fields = {"body", "subject"}
            if blocked_fields & set(vals.keys()):
                # Si es creación/ajuste inmediato, permitir.
                if self._is_recent_creation_phase():
                    return super().write(vals)
                # Fuera de la ventana de creación: solo superusuario o grupo.
                if not self._can_modify_chatter():
                    raise AccessError("No tienes permiso para editar mensajes/notas del chatter.")
        return super().write(vals)

    def unlink(self):
        """
        Bloquear eliminación de mensajes/notas visibles para todos,
        excepto superusuario o grupo whitelist.
        """
        if self._contains_user_comments() and not self._can_modify_chatter():
            raise AccessError("No tienes permiso para eliminar mensajes/notas del chatter.")
        return super().unlink()
