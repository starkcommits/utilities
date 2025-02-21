import frappe
import requests
import time
import json
import random

from typing import Optional, Dict, Any

@frappe.whitelist()
def make_an_order(product_name: str, provider_id: str, processor_name: str, 
                  order_amount: float, mobile_number: str, channel_partner: str):

    try:
        order_amount = float(order_amount)

        # Check Available Balance
        partner_wallet = frappe.get_doc("Partner Wallet",{
            "channel_partner":channel_partner
        })
        available_balance = partner_wallet.balance

        if available_balance < order_amount:
            frappe.throw("Insufficient Balance")

        # Fetch Channel Partner Discount
        fee_details = frappe.get_all(
            "Product Pricing",
            filters={"parent": channel_partner, "product_name": product_name},
            fields=["discount_type", "discount_amount","plateform_fee_type","plateform_fee"]
        )

        # Calculate transaction amount with discount
        transaction_amount = order_amount
        discount_value = 0
        discount_type = "None"

        plateform_fee_value = 0
        plateform_fee_type = "None"

        if fee_details:
            fee = fee_details[0]
            discount_value = float(fee.get("discount_amount", 0))
            discount_type = fee.get("discount_type", "None")

            if discount_type == "Percentage":
                discount_value = order_amount * discount_value / 100
                transaction_amount = order_amount - discount_value
            elif discount_type == "Fixed":
                transaction_amount = order_amount - discount_value
            
            plateform_fee_value = float(fee.get("plateform_fee", 0))
            plateform_fee_type = fee.get("plateform_fee_type","None")

            if plateform_fee_type == "Percentage":
                plateform_fee_value = order_amount * plateform_fee_value / 100
                transaction_amount = transaction_amount + plateform_fee_value
            elif plateform_fee_type == "Fixed":
                transaction_amount = transaction_amount + plateform_fee_value
            
        # Create an order
        order = frappe.get_doc({
            "doctype": "Orders",
            "order_amount": order_amount,
            "product_name": product_name,
            "mobile_number": mobile_number,
            "processor": processor_name,
            "channel": "Android",
            "channel_partner": channel_partner,
            "order_status": "Created"
        })
        order.insert(ignore_permissions=True)

        txn_log = frappe.get_doc({
            "doctype": "Payment Transaction Logs",
            "channel_partner": channel_partner,
            "product_name":product_name,
            "order_id":order.name,
            "order_amount": order_amount,
            "discount":discount_value,
            "plateform_fee":plateform_fee_value,
            "transaction_type": "Debit (Hold)",
            "transaction_amount":transaction_amount,
            "closing_balance" : available_balance - transaction_amount,
            "status": "Created"
        })
        txn_log.insert(ignore_permissions=True)

        order.transaction_id=txn_log.name
        order.save(ignore_permissions=True)

        # Send request to payment processor
        processor = frappe.get_doc("Processor", processor_name)
        method = next((m for m in processor.api_methods if m.method_name == "Make Payment"), None)

        if not method:
            raise frappe.ValidationError("Make Payment method not found in processor configuration")

        url = processor.base_url + method.method_end_point
        api_token = next((config.api_key for config in processor.api_config if config.key_name == "API Token"), None)

        if not api_token:
            raise frappe.ValidationError("API Token not found in processor configuration")

        payload = {
            "api_token": api_token,
            "provider_id": provider_id,
            "amount": order_amount,
            "number": mobile_number,
            "client_id": order.name,
            "environment": "UAT"
        }
        response = requests.get(url, params=payload)
        time.sleep(2)
        frappe.log_error(
            title="API Request Response",
            message=f"Request Body: {payload}, Response Body: {response.text}",
            reference_doctype="Orders",  # The related document type
            reference_name=order.name  # The related order ID
        )


        response_data = response.json()
        if response_data["status"] == "success":
            # Create a final transaction log (Hold amount)
            txn_log.status = "Completed"
            txn_log.transaction_type = "Debit (Final)"
            txn_log.save(ignore_permissions=True)

            order.order_status="Completed"
            order.save(ignore_permissions=True)

            frappe.db.commit()
            return {"status": "success", "transaction_id":txn_log.name}
        elif response_data["status"] == "pending":
            txn_log.save(ignore_permissions=True)
            frappe.db.commit()
            return {"status": "pending", "message": "Transaction processing", "order_id": order.name, "transaction_id": txn_log.name, "pay_id": response_data["payid"]}
        
        else:
            # Mark transaction as failed
            txn_log.status = "Reversed"
            txn_log.transaction_type = "Credit Reversal"
            txn_log.closing_balance = available_balance + transaction_amount
            txn_log.save(ignore_permissions=True)

            order.order_status="Canceled"
            order.save(ignore_permissions=True)

            frappe.db.commit()
            
            return {"status": "failed", "message": "Transaction failed"}

    except Exception as e:
        frappe.log_error("Order Processing Error", str(e))
        frappe.throw(str(e))



@frappe.whitelist(allow_guest=True)
def payment_webhook():
    """Webhook listener for payment status updates from the payment processor."""
    try:
        data = json.loads(frappe.request.data)
        order_id = data.get("client_id")
        status = data.get("status")

        if not order_id:
            frappe.throw("Invalid webhook data: Missing Order ID")

        # Fetch order and pending transaction log
        order = frappe.get_doc("Orders", order_id)
        
        if not order or order.order_status!="Processing":
            frappe.throw("No pending order found with this Order ID")

        txn_log = frappe.get_doc("Payment Transaction Logs",order.transaction_id)

        if not txn_log or txn_log.status!="Processing":
            frappe.throw("No pending txn found with this order ID")

        if status.lower() == "success":
            # Finalize the transaction
            txn_log.status = "Completed"
            txn_log.transaction_type = "Debit (Final)"
            txn_log.save(ignore_permissions=True)

            order.order_status = "Completed"
            order.save(ignore_permissions=True)

        else:
            txn_log.status = "Reversed"
            txn_log.transaction_type = "Credit Reversal"
            txn_log.save(ignore_permissions=True)

            order.order_status = "Canceled"
            order.save(ignore_permissions=True)

        frappe.db.commit()
        return {"status": "success", "message": "Transaction updated successfully"}

    except Exception as e:
        frappe.log_error("Webhook Processing Error", str(e))
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def topup(amount,channel_partner):
    amount = float(amount)

    order = frappe.get_doc({
        "doctype":"Orders",
        "product_name":"Wallet Top Up",
        "order_amount":amount,
        "channel_partner":channel_partner,
        "channel":"Web"
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
        "status": "Reversed"
    })
    transaction.insert(ignore_permissions=True)

    order.order_status="Completed"
    order.transaction_id=transaction.name
    order.order_remark="Wallet recharged successfully"
    order.save(ignore_permissions=True)

    frappe.db.commit()
    return {"Wallet recharged successfully"}

# def get_available_balance(channel_partner):
#     """Calculate available balance based on transaction log."""
#     total_credits = frappe.db.sql("""
#         SELECT SUM(transaction_amount) FROM `tabPayment Transaction Logs`
#         WHERE channel_partner = %s AND transaction_type IN ('Credit (Top-up)', 'Credit Reversal')
#     """, (channel_partner))[0][0] or 0

#     total_debits = frappe.db.sql("""
#         SELECT SUM(transaction_amount) FROM `tabPayment Transaction Logs`
#         WHERE channel_partner = %s AND transaction_type IN ('Debit (Hold)', 'Debit (Final)')
#     """, (channel_partner))[0][0] or 0

#     return total_credits - total_debits

# def get_closing_balance(channel_partner):
#     """Fetch the latest closing balance from the transaction log."""
#     latest_balance = frappe.db.sql("""
#         SELECT closing_balance FROM `tabPayment Transaction Logs`
#         WHERE channel_partner = %s
#         ORDER BY creation DESC
#         LIMIT 1
#     """, (channel_partner,))

#     return latest_balance[0][0] if latest_balance else 0  # Default to 0 if no transactions exist


@frappe.whitelist()
def bulk_recharge():
    try:
        
        while (True):
            mobile_number = f"74519{random.randint(10000, 99999)}"  # Ensure uniqueness
            make_an_order("Airtel", "1", "Scriza", 10, mobile_number, "Tata")

    except Exception as e:
        frappe.log_error("Bulk Recharges Failed", str(e))
        frappe.throw(str(e))

    return {"message": "Recharge Successful"}

  
@frappe.whitelist()
def delete_record():
    # Unlink transaction IDs in Orders
    for order in frappe.get_all("Orders", pluck="name"):
        frappe.db.set_value("Orders", order, "transaction_id", None)

    frappe.db.commit()

    # Unlink order IDs in Payment Transaction Logs
    for txn in frappe.get_all("Payment Transaction Logs", pluck="name"):
        frappe.db.set_value("Payment Transaction Logs", txn, "order_id", None)

    frappe.db.commit()

    # Delete Payment Transaction Logs first (child table)
    frappe.db.delete("Payment Transaction Logs")

    # Delete Orders (parent table)
    frappe.db.delete("Orders")

    frappe.db.commit()

