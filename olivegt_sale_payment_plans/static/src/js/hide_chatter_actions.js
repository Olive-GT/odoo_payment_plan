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

    const TEXT_MATCHES = new Set([
        "editar",
        "eliminar",
        "edit",
        "delete",
    ]);

    function hideOnce(root) {
        if (!root || !root.querySelectorAll) return;
        // Hide by attribute selectors first
        root.querySelectorAll(HIDE_SELECTOR).forEach((el) => {
            el.style.setProperty("display", "none", "important");
        });

        // Fallback: hide by visible text in case attributes change or are translated
        const candidates = root.querySelectorAll(
            '.o-mail-Message-moreMenu [role="menuitem"], .o_thread_message .dropdown-menu [role="menuitem"], .o_thread_message .dropdown-menu a, .o-mail-Message-moreMenu a'
        );
        candidates.forEach((el) => {
            const text = (el.textContent || "").trim().toLowerCase();
            if (TEXT_MATCHES.has(text)) {
                el.style.setProperty("display", "none", "important");
            }
        });
    }

    function start() {
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
