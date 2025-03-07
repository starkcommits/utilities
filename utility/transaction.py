import frappe
from frappe.utils import cint

def create_transaction(doc):
    """Create a transaction and safely deduct wallet balance using DB row locking"""

    try:
        # Fetch & Lock Wallet Row
        wallet_data = frappe.db.sql("""
            SELECT name, balance FROM `tabPartner Wallet`
            WHERE channel_partner = %s AND status = "Active"
            FOR UPDATE
        """, (doc.channel_partner,), as_dict=True)

        if not wallet_data:
            doc.order_status = "Canceled"
            doc.order_remark = "No active wallet found."
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw("No active wallet found.")

        wallet_name = wallet_data[0]["name"]
        available_balance = wallet_data[0]["balance"]

        # Calculate transaction amount
        product_pricing = frappe.db.sql("""
            SELECT discount_type, discount_amount, plateform_fee_type, plateform_fee
            FROM `tabProduct Pricing`
            WHERE parent = %s AND product_name = %s
        """, (doc.channel_partner, doc.product_name), as_dict=True)

        if not product_pricing:
            doc.order_status = "Canceled"
            doc.order_remark = "No pricing found for this product."
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw("No pricing found for this product.")

        pricing = product_pricing[0]
        discount_value = cint(pricing["discount_amount"])
        plateform_fee_value = cint(pricing["plateform_fee"])

        # Apply Discount & Platform Fee
        transaction_amount = doc.order_amount
        if pricing["discount_type"] == "Percentage":
            discount_value = (doc.order_amount * discount_value) / 100
        transaction_amount -= discount_value

        if pricing["plateform_fee_type"] == "Percentage":
            plateform_fee_value = (doc.order_amount * plateform_fee_value) / 100
        transaction_amount += plateform_fee_value

        # Ensure Sufficient Balance
        if available_balance < transaction_amount:
            doc.order_status = "Canceled"
            doc.order_remark = "Insufficient balance."
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw("Insufficient balance. Please recharge your wallet.")

        # Deduct Wallet Balance (Row is locked, so no race condition)
        new_balance = available_balance - transaction_amount
        frappe.db.sql("""
            UPDATE `tabPartner Wallet`
            SET balance = %s
            WHERE name = %s
        """, (new_balance, wallet_name))

        # Insert Transaction Log
        txn_log = frappe.get_doc({
            "doctype": "Payment Transaction Logs",
            "channel_partner": doc.channel_partner,
            "product_name": doc.product_name,
            "order_id": doc.name,
            "order_amount": doc.order_amount,
            "discount": discount_value,
            "plateform_fee": plateform_fee_value,
            "transaction_type": "Debit (Hold)",
            "transaction_amount": transaction_amount,
            "closing_balance": new_balance,
            "status": "Processing"
        })
        txn_log.insert(ignore_permissions=True)
        
        # frappe.db.set_value("Orders", doc.name, {
        #     "order_status":"Processing",
        #     "transaction_id":txn_log.name
        # })

        doc.order_status = "Processing"
        doc.transaction_id = txn_log.name
        doc.db_update()

        frappe.db.commit()  # ✅ Commit all changes atomically

    except Exception as e:
        frappe.db.rollback()  # ✅ Rollback if an error occurs
        frappe.log_error(f"Transaction Error: {str(e)}", "Transaction Failure")
        raise

# def create_transaction(doc):
#     """Create a transaction and safely deduct wallet balance using DB row locking"""

#     try:
#         # Prevent Recursive Trigger
#         if hasattr(doc, '_transaction_processing') and doc._transaction_processing:
#             return

#         doc._transaction_processing = True  # Set flag

#         # Fetch & Lock Wallet Row
#         wallet_data = frappe.db.sql("""
#             SELECT name, balance FROM `tabPartner Wallet`
#             WHERE channel_partner = %s AND status = "Active"
#             FOR UPDATE
#         """, (doc.channel_partner,), as_dict=True)

#         if not wallet_data:
#             doc.order_status = "Canceled"
#             doc.order_remark = "No active wallet found."
#             doc.db_update()  # ✅ Use db_update() instead of save() to prevent hooks triggering again
#             frappe.db.commit()
#             frappe.throw("No active wallet found.")

#         wallet_name = wallet_data[0]["name"]
#         available_balance = wallet_data[0]["balance"]

#         # Calculate transaction amount
#         product_pricing = frappe.db.sql("""
#             SELECT discount_type, discount_amount, plateform_fee_type, plateform_fee
#             FROM `tabProduct Pricing`
#             WHERE parent = %s AND product_name = %s
#         """, (doc.channel_partner, doc.product_name), as_dict=True)

#         if not product_pricing:
#             doc.order_status = "Canceled"
#             doc.order_remark = "No pricing found for this product."
#             doc.db_update()
#             frappe.db.commit()
#             frappe.throw("No pricing found for this product.")

#         pricing = product_pricing[0]
#         discount_value = cint(pricing["discount_amount"])
#         plateform_fee_value = cint(pricing["plateform_fee"])

#         # Apply Discount & Platform Fee
#         transaction_amount = doc.order_amount
#         if pricing["discount_type"] == "Percentage":
#             discount_value = (doc.order_amount * discount_value) / 100
#         transaction_amount -= discount_value

#         if pricing["plateform_fee_type"] == "Percentage":
#             plateform_fee_value = (doc.order_amount * plateform_fee_value) / 100
#         transaction_amount += plateform_fee_value

#         # Ensure Sufficient Balance
#         if available_balance < transaction_amount:
#             doc.order_status = "Canceled"
#             doc.order_remark = "Insufficient balance."
#             doc.db_update()
#             frappe.db.commit()
#             frappe.throw("Insufficient balance. Please recharge your wallet.")

#         # Deduct Wallet Balance (Row is locked, so no race condition)
#         new_balance = available_balance - transaction_amount
#         frappe.db.sql("""
#             UPDATE `tabPartner Wallet`
#             SET balance = %s
#             WHERE name = %s
#         """, (new_balance, wallet_name))

#         # Insert Transaction Log
#         txn_log = frappe.get_doc({
#             "doctype": "Payment Transaction Logs",
#             "channel_partner": doc.channel_partner,
#             "product_name": doc.product_name,
#             "order_id": doc.name,
#             "order_amount": doc.order_amount,
#             "discount": discount_value,
#             "plateform_fee": plateform_fee_value,
#             "transaction_type": "Debit (Hold)",
#             "transaction_amount": transaction_amount,
#             "closing_balance": new_balance,
#             "status": "Processing"
#         })
#         txn_log.insert(ignore_permissions=True)

#         doc.order_status = "Processing"
#         doc.transaction_id = txn_log.name
#         doc.db_update()  # ✅ Use db_update() instead of save()

#         frappe.db.commit()  # ✅ Commit all changes atomically

#     except Exception as e:
#         frappe.db.rollback()  # ✅ Rollback if an error occurs
#         frappe.log_error(f"Transaction Error: {str(e)}", "Transaction Failure")
#         raise

#     finally:
#         # Remove flag after execution
#         if hasattr(doc, '_transaction_processing'):
#             del doc._transaction_processing


def make_transaction(doc, method):
    # Guard clause to prevent recursive updates
    if hasattr(doc, '_payment_transaction_logs_update_in_progress') and doc._payment_transaction_logs_update_in_progress:
        return
    
    try:
        # Set flag to prevent recursive calls
        doc._payment_transaction_logs_update_in_progress = True
        
        if doc.order_status == "Created":
            create_transaction(doc)
        elif doc.order_status == "Completed" and not doc.order_remark:
            # transaction = frappe.db.set_value(
            #     "Payment Transaction Logs",
            #     doc.transaction_id,
            #     {
            #         "status": "Completed",
            #         "transaction_type": "Debit (Final)"
            #     },
            #     update_modified=False
            # )
            # frappe.db.commit()

            transaction = frappe.get_doc("Payment Transaction Logs",doc.transaction_id)
            transaction.status="Completed"
            transaction.transaction_type="Debit (Final)"

            transaction.save(ignore_permissions=True)
            frappe.db.commit()

            doc.order_remark= "Order created Successfully."
            doc.db_update()
            # doc.save(ignore_permissions=True)
            frappe.db.commit()
            doc.reload()

        elif doc.order_status == "Canceled":
            frappe.db.set_value(
                "Payment Transaction Logs",
                doc.transaction_id,
                {
                    "status": "Reversed",
                    "transaction_type": "Credit Reversal"
                },
                update_modified=False
            )
            frappe.db.commit()
            doc.reload()
    finally:
        # Always clear the flag regardless of success or failure
        if hasattr(doc, '_payment_transaction_logs_update_in_progress'):
            doc._payment_transaction_logs_update_in_progress = False 