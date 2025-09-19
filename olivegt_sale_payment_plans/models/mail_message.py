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
        """Return True if any message in the recordset is a user comment.

        We consider a 'user comment' those with message_type == 'comment'.
        System log/tracking/notification messages usually have other types
        (e.g., 'notification', 'email', etc.) and should be allowed to be
        deleted by business flows (like resetting a document to draft).
        """
        # Ensure we don't prefetch too much; read only the needed field.
        types = set(self.mapped("message_type"))
        return "comment" in types

    def write(self, vals):
        # Permitir modificaciones necesarias para envío/actualización de mensajes.
        # Si más adelante se requiere limitar ediciones de comentarios, se puede
        # reintroducir una validación específica aquí.
        return super().write(vals)

    def unlink(self):
        # Only block deletion of user comments; allow system/notification messages to be removed.
        if self._contains_user_comments() and not self.with_user(self._original_uid())._can_modify_chatter():
            raise AccessError("No tienes permiso para eliminar mensajes del chatter.")
        return super().unlink()
