import frappe

@frappe.whitelist()
def do_topup(amount,channel_partner):

    order = frappe.get_doc({
        "doctype":"Orders",
        "product_name":"Wallet Top Up",
        "order_amount":amount,
        "channel_partner":channel_partner,
        "channel":"web"
    })
    order.insert(ignore_permissions=True)
    
    transaction = frappe.get_doc({
        "doctype":"Payment Transaction Logs",
        "source_docname":"Orders",
        "order_id":order.name,
        "channel_partner": order.channel_partner,
        "channel": order.channel,
        "product_name": order.product_name,
        "order_amount": order.order_amount,
        "transaction_amount": order.order_amount,
        "discount": 0,
        "transaction_type":"Credit (Top-up)",
        "status": "Successful",
    })
    transaction.insert(ignore_permissions=True)

    wallet = frappe.get_doc(
        "Partner Wallet",
        {"channel_partner": "Tata"}
    )
    wallet.balance+=amount
    wallet.save(ignore_permissions=True)

    order.order_status="Successful"
    order.transaction_id=transaction.name
    order.order_remark="Wallet recharged successfully"
    order.save(ignore_permissions=True)

    transaction.closing_balance=wallet.balance
    transaction.save(ignore_permissions=True)

    frappe.db.commit()
    return transaction

@frappe.whitelist()
def get_available_balance(channel_partner):
    """Calculate available balance based on transaction log."""
    total_credits = frappe.db.sql("""
        SELECT SUM(order_amount) FROM `tabPayment Transaction Logs`
        WHERE channel_partner = %s AND transaction_type IN ('Credit (Top-up)', 'Credit Reversal')
    """, (channel_partner))[0][0] or 0

    total_debits = frappe.db.sql("""
        SELECT SUM(order_amount) FROM `tabPayment Transaction Logs`
        WHERE channel_partner = %s AND transaction_type IN ('Debit (Hold)', 'Debit (Final)')
    """, (channel_partner))[0][0] or 0

    return total_credits - total_debits

