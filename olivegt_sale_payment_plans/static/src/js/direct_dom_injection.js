/**
 * This is a standalone, self-executing script that can be injected into any page
 * to add overdue payment information to reconciliation dialogs
 */
(function() {
    // Function to inject the HTML directly
    function injectOverdueInfo(dialogElement, overdueData) {
        // Check if we've already injected
        if (dialogElement.querySelector('.payment_plan_overdue_info')) {
            return;
        }
        
        // Create the overdue information panel
        const overduePanel = document.createElement('div');
        overduePanel.className = 'payment_plan_overdue_info alert alert-warning mb-3';
        overduePanel.innerHTML = `
            <h5 class="alert-heading">⚠️ Overdue Payment Information</h5>
            <table class="table table-sm table-borderless mb-0">
                <tr>
                    <td class="text-right"><strong>Overdue Days:</strong></td>
                    <td><span class="badge badge-danger">${overdueData.overdue_days || 0}</span></td>
                </tr>
                <tr>
                    <td class="text-right"><strong>Interest Amount:</strong></td>
                    <td>${overdueData.interest_amount || 0.0} ${overdueData.currency_symbol || ''}</td>
                </tr>
                <tr>
                    <td class="text-right"><strong>Total with Interest:</strong></td>
                    <td><strong>${overdueData.total_with_interest || 0.0} ${overdueData.currency_symbol || ''}</strong></td>
                </tr>
            </table>
            <hr/>
            <div class="mt-2">
                <strong>Important:</strong> This payment is overdue. The total amount with interest 
                (<strong>${overdueData.total_with_interest || 0.0} ${overdueData.currency_symbol || ''}</strong>) 
                must be paid to fully reconcile this line.
            </div>
        `;
        
        // Find a suitable injection point
        const modalBody = dialogElement.querySelector('.modal-body');
        if (modalBody) {
            // Insert at the beginning of the modal body
            modalBody.insertBefore(overduePanel, modalBody.firstChild);
        }
    }
    
    // Set up a mutation observer to watch for the dialog
    const observer = new MutationObserver(mutations => {
        mutations.forEach(mutation => {
            if (mutation.type === 'childList' && mutation.addedNodes.length) {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType !== 1) return; // Skip non-element nodes
                    
                    // Look for reconciliation dialog
                    const dialogTitle = node.querySelector('.modal-title');
                    if (dialogTitle && dialogTitle.textContent.includes('Reconcile Payment')) {
                        const dialog = dialogTitle.closest('.modal');
                        if (dialog) {
                            // Extract payment plan line ID or code
                            let lineId = null;
                            let lineCode = null;
                            
                            // Try to get from heading
                            const heading = dialog.querySelector('h1');
                            if (heading && heading.textContent.trim().match(/PPL\/\d+\/\d+/)) {
                                lineCode = heading.textContent.trim();
                            }
                            
                            // Try to get from hidden fields or data attributes
                            const hiddenField = dialog.querySelector('[name="payment_plan_line_id"]');
                            if (hiddenField) {
                                lineId = hiddenField.value;
                            }
                            
                            // If we have either ID or code, fetch the overdue data
                            if (lineId || lineCode) {
                                // Use DOM dataset to avoid adding jQuery as dependency
                                const params = {
                                    jsonrpc: "2.0",
                                    method: "call",
                                    params: {
                                        model: "payment.plan.line",
                                        method: "search_read",
                                        domain: lineId ? [["id", "=", lineId]] : [["payment_plan_id.name", "=", lineCode]],
                                        fields: ["overdue_days", "interest_amount", "total_with_interest", "currency_id"],
                                        limit: 1
                                    },
                                    id: Math.floor(Math.random() * 1000000)
                                };
                                
                                // Make the RPC call
                                fetch("/web/dataset/call_kw", {
                                    method: "POST",
                                    headers: {
                                        "Content-Type": "application/json",
                                    },
                                    body: JSON.stringify(params),
                                })
                                .then(response => response.json())
                                .then(data => {
                                    if (data.result && data.result.length && data.result[0].overdue_days > 0) {
                                        // We have overdue data, inject it
                                        injectOverdueInfo(dialog, {
                                            overdue_days: data.result[0].overdue_days,
                                            interest_amount: data.result[0].interest_amount,
                                            total_with_interest: data.result[0].total_with_interest,
                                            currency_symbol: data.result[0].currency_id[1] || ""
                                        });
                                    }
                                })
                                .catch(error => console.error("Error fetching overdue data:", error));
                            }
                        }
                    }
                });
            }
        });
    });
    
    // Start observing
    observer.observe(document.body, { childList: true, subtree: true });
})();
