import frappe

def update_wallet(doc, method):
    """Update wallet balance safely for reversals or top-ups using DB row locking"""

    try:
        # Fetch & Lock Wallet Row
        wallet_data = frappe.db.sql("""
            SELECT name, balance FROM `tabPartner Wallet`
            WHERE channel_partner = %s FOR UPDATE
        """, (doc.channel_partner,), as_dict=True)

        if not wallet_data:
            frappe.throw("No wallet found for this channel partner.")

        wallet_name = wallet_data[0]["name"]
        wallet_balance = wallet_data[0]["balance"]
        new_balance = wallet_balance  # Default: No change

        # **Only handle reversals or top-ups**
        if doc.status == "Reversed" or (doc.status == "Completed" and doc.product_name == "Wallet Top Up"):
            new_balance = wallet_balance + doc.transaction_amount

            # Update Wallet Balance
            frappe.db.sql("""
                UPDATE `tabPartner Wallet`
                SET balance = %s
                WHERE name = %s
            """, (new_balance, wallet_name))

            # Update Payment Transaction Logs
            frappe.db.sql("""
                UPDATE `tabPayment Transaction Logs`
                SET closing_balance = %s
                WHERE name = %s
            """, (new_balance, doc.name))

        frappe.db.commit()  # ✅ Commit at the end

    except Exception as e:
        frappe.db.rollback()  # ✅ Rollback in case of failure
        frappe.log_error(f"Wallet Update Error: {str(e)}", "Wallet Update Failure")
        raise