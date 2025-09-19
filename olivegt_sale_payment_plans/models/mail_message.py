from odoo import models, SUPERUSER_ID, fields
from odoo.exceptions import AccessError


class MailMessage(models.Model):
    _inherit = "mail.message"

    # --- Helpers -------------------------------------------------------------

    def _original_uid(self):
        """UID real (evita que sudo() o contextos oculten al usuario real)."""
        return self.env.context.get("uid", self.env.uid)

    def _is_superuser(self):
        return self._original_uid() == SUPERUSER_ID

    def _contains_user_comments(self):
        """
        True si la selección incluye contenido visible al usuario (mensajes/notes/emails).
        - 'comment' (mensajes + notas)
        - 'email'
        - 'notification' con subtype interno (nota interna)
        """
        types = set(self.mapped("message_type"))
        if "comment" in types or "email" in types:
            return True
        for msg in self:
            if (
                msg.message_type == "notification"
                and msg.subtype_id
                and getattr(msg.subtype_id, "internal", False)
            ):
                return True
        return False

    def _is_recent_creation_phase(self, threshold_seconds=30):
        """
        Permite solo escrituras técnicas inmediatamente tras la creación,
        típicas del flujo de message_post. Mucho más estricta:
        - Requiere que TODOS los mensajes sean muy recientes, y
        - Requiere flags de posteo conocidos (no 'default_*').
        """
        post_flags = (
            "mail_post_autofollow",
            "mail_create_nosubscribe",
            "mail_post_autofollow_partner_ids",
        )
        if not any(self.env.context.get(flag) for flag in post_flags):
            return False

        now = fields.Datetime.now()
        for msg in self:
            if not msg.create_date:
                return False
            if (now - msg.create_date).total_seconds() > threshold_seconds:
                return False
        return True

    # --- Guard rails de seguridad -------------------------------------------

    def write(self, vals):
        """
        Política:
        - Se permite crear libremente (create no se toca).
        - Tras creado, NO se puede editar contenido visible (body/subject) NUNCA,
          salvo superusuario, o si estamos en la ventana estricta de creación.
        - Otras escrituras técnicas (no body/subject) siguen permitidas para no
          romper contadores, notificaciones, etc.
        """
        if self._contains_user_comments():
            blocked_fields = {"body", "subject"}
            if blocked_fields & set(vals.keys()):
                # Solo permitimos si es superusuario o si aún estamos en la fase
                # de creación MUY reciente del flujo de posteo.
                if not (self._is_superuser() or self._is_recent_creation_phase()):
                    raise AccessError("No tienes permiso para editar mensajes/notas del chatter.")
        return super().write(vals)

    def unlink(self):
        """
        Política:
        - NO se puede eliminar mensajes/notas visibles del chatter.
        - ÚNICA excepción: superusuario (por tareas de mantenimiento).
        """
        if self._contains_user_comments() and not self._is_superuser():
            raise AccessError("No tienes permiso para eliminar mensajes/notas del chatter.")
        return super().unlink()
