from odoo import models, SUPERUSER_ID
from odoo.exceptions import AccessError


class MailMessage(models.Model):
    _inherit = "mail.message"

    def _original_uid(self):
        """Return the original user id from context if present.
        This helps avoid sudo() masking the real user during checks.
        """
        return self.env.context.get("uid", self.env.uid)

    def _can_modify_chatter(self):
        """Centralized guard to decide if the real user can edit/delete chatter.

        Allowed when:
        - It's the superuser, or
        - The user belongs to the optional whitelist group
          'olivegt_sale_payment_plans.group_chatter_editors'.
        """
        uid = self._original_uid()
        if uid == SUPERUSER_ID:
            return True
        user = self.env["res.users"].browse(uid)
        return user.has_group("olivegt_sale_payment_plans.group_chatter_editors")

    def _contains_user_comments(self):
        """Return True if any message is user-visible content (messages or notes).

        Protected content includes:
        - message_type 'comment' (user messages and internal notes)
        - message_type 'email' (emails should not be deletable by regular users)
        - message_type 'notification' with internal subtype (internal notes)
        System log/tracking notifications remain deletable to allow business flows.
        """
        types = set(self.mapped("message_type"))
        if "comment" in types or "email" in types:
            return True
        # Check internal notification notes via subtype
        for msg in self:
            if (
                msg.message_type == "notification"
                and msg.subtype_id
                and getattr(msg.subtype_id, "internal", False)
            ):
                return True
        return False

    def write(self, vals):
        # Bloquear edición de mensajes/notas visibles, salvo que se autorice explícitamente por contexto.
        if self._contains_user_comments() and not self.env.context.get("allow_chatter_write"):
            raise AccessError("No tienes permiso para editar mensajes/notas del chatter.")
        return super().write(vals)

    def unlink(self):
        # Bloquear eliminación de mensajes/notas visibles, salvo autorización explícita por contexto.
        if self._contains_user_comments() and not self.env.context.get("allow_chatter_unlink"):
            raise AccessError("No tienes permiso para eliminar mensajes/notas del chatter.")
        return super().unlink()
