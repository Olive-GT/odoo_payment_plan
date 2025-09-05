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

    def write(self, vals):
        # Block any attempt to modify chatter messages unless explicitly allowed.
        if not self.with_user(self._original_uid())._can_modify_chatter():
            raise AccessError(
                "No tienes permiso para modificar mensajes del chatter."
            )
        return super().write(vals)

    def unlink(self):
        # Block any attempt to delete chatter messages unless explicitly allowed.
        if not self.with_user(self._original_uid())._can_modify_chatter():
            raise AccessError(
                "No tienes permiso para eliminar mensajes del chatter."
            )
        return super().unlink()
