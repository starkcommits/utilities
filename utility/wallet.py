import frappe

def update_wallet(doc, method):
    # Guard clause to prevent recursive updates
    if hasattr(doc, '_wallet_update_in_progress') and doc._wallet_update_in_progress:
        return
        
    try:
        # Set flag to prevent recursive calls
        doc._wallet_update_in_progress = True
        
        # Fetch Partner Wallet safely
        partner_wallet = frappe.get_all(
            "Partner Wallet",
            filters={"channel_partner": doc.channel_partner},
            fields=["name", "balance"]
        )
        
        if not partner_wallet:
            frappe.throw(f"No wallet found for channel partner: {doc.channel_partner}")
        
        partner_wallet = frappe.get_doc("Partner Wallet", partner_wallet[0]["name"])
        
        # Case 1: When Transaction is Created
        if doc.status == "Created":
            partner_wallet.balance -= doc.transaction_amount
            partner_wallet.save(ignore_permissions=True)
            frappe.db.commit()
            # Update order status if exists
            order = frappe.get_all(
                "Orders",
                filters={"transaction_id": doc.name},
                fields=["name", "order_status"]
            )
            
            if order:
                order_doc = frappe.get_doc("Orders", order[0]["name"])
                order_doc.order_status = "Processing"
                order_doc.save(ignore_permissions=True)
                frappe.db.commit()
            
            # Update transaction status and balance without triggering events
            frappe.db.set_value(
                "Payment Transaction Logs",
                doc.name,
                {
                    "status": "Processing",
                    "closing_balance": partner_wallet.balance
                },
                update_modified=False
            )

            doc.reload()
        # Case 2: When Transaction is Reversed
        elif doc.status == "Reversed" or (doc.status == "Completed" and doc.product_name == "Wallet Top Up"):
            partner_wallet.balance += doc.transaction_amount
            partner_wallet.save(ignore_permissions=True)
            frappe.db.commit()
            # Update closing balance without triggering events
            frappe.db.set_value(
                "Payment Transaction Logs",
                doc.name,
                {"closing_balance": partner_wallet.balance},
                update_modified=False
            )
            doc.reload()

        frappe.db.commit()
        
    finally:
        # Always remove the flag, even if an error occurs
        doc._wallet_update_in_progress = False