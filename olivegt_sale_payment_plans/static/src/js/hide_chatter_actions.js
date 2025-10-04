/**
 * Hide Edit/Delete options from mail message more menu (visual only).
 * Works by observing DOM mutations and applying display:none to matching items.
 * Note: This is a UI-only deterrent and does not enforce permissions.
 */
(function () {
    "use strict";

    const HIDE_SELECTOR = `
        .o-mail-Message-moreMenu [role="menuitem"][title="Editar"],
        .o-mail-Message-moreMenu [role="menuitem"][title="Eliminar"],
        .o-mail-Message-moreMenu [role="menuitem"][title="Edit"],
        .o-mail-Message-moreMenu [role="menuitem"][title="Delete"],
        .o_thread_message .dropdown-menu [title="Editar"],
        .o_thread_message .dropdown-menu [title="Eliminar"],
        .o_thread_message .dropdown-menu [title="Edit"],
        .o_thread_message .dropdown-menu [title="Delete"]
    `;

    // Common labels to hide (normalized to lowercase)
    const TEXT_MATCHES = new Set(["editar", "eliminar", "edit", "delete", "delete message", "remove", "modify"]);

    function hideOnce(root) {
        if (!root || !root.querySelectorAll) return;
        // Hide by attribute selectors first
        root.querySelectorAll(HIDE_SELECTOR).forEach((el) => {
            el.style.setProperty("display", "none", "important");
        });

        // Fallback: hide by visible text in case attributes change or are translated
        const candidates = root.querySelectorAll(
            '.o-mail-Message-moreMenu [role="menuitem"], .o_thread_message .dropdown-menu [role="menuitem"], .o_thread_message .dropdown-menu a, .o-mail-Message-moreMenu a, .o_popover.o-mail-Message-moreMenu [role="menuitem"]'
        );
        candidates.forEach((el) => {
            const text = (el.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
            // Match if exactly the label or starts with the label (e.g., "Eliminar mensaje")
            for (const label of TEXT_MATCHES) {
                if (text === label || text.startsWith(label + " ")) {
                    el.style.setProperty("display", "none", "important");
                    return;
                }
            }
            // Also hide by icon hints if present
            const hasTrash = !!el.querySelector('.fa-trash, .oi-trash');
            const hasPencil = !!el.querySelector('.fa-pencil, .oi-pencil');
            if (hasTrash || hasPencil) {
                const title = (el.getAttribute('title') || '').toLowerCase();
                if (title.includes('eliminar') || title.includes('delete') || title.includes('editar') || title.includes('edit')) {
                    el.style.setProperty("display", "none", "important");
                }
            }
        });
    }

    function start() {
        // Tiny marker to confirm asset loaded
        if (!window.__olive_hide_chatter_loaded) {
            window.__olive_hide_chatter_loaded = true;
            // eslint-disable-next-line no-console
            console.debug('[olivegt_sale_payment_plans] hide_chatter_actions loaded');
        }
        hideOnce(document);
        const mo = new MutationObserver((muts) => {
            for (const m of muts) {
                for (const n of m.addedNodes) {
                    if (n instanceof HTMLElement) hideOnce(n);
                }
            }
        });
        mo.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
