import frappe
import requests
import time
import json
from typing import Optional, Dict, Any

@frappe.whitelist()
def make_an_order(product_name: str, provider_id: str, processor_name: str, 
                  order_amount: float, mobile_number: str, channel_partner: str):

    try:
        order_amount = float(order_amount)

        # Check Available Balance
        available_balance = get_closing_balance(channel_partner)

        if available_balance < order_amount:
            frappe.throw("Insufficient Balance")

        # Fetch Channel Partner Discount
        discount_details = frappe.get_all(
            "Product Pricing",
            filters={"parent": "Tata", "product_name": product_name},
            fields=["discount_type", "discount_amount"]
        )

        # Calculate transaction amount with discount
        transaction_amount = order_amount
        discount_value = 0
        discount_type = "None"

        if discount_details:
            discount = discount_details[0]
            discount_value = float(discount.get("discount_amount", 0))
            discount_type = discount.get("discount_type", "None")

            if discount_type == "Percentage":
                transaction_amount = order_amount * (1 - discount_value / 100)
            elif discount_type == "Fixed":
                transaction_amount = order_amount - discount_value

        txn_log = frappe.get_doc({
            "doctype": "Payment Transaction Logs",
            "channel_partner": channel_partner,
            "product_name":product_name,
            "transaction_type": "Debit (Hold)",
            "order_amount": order_amount,
            "discount":discount_value,
            "transaction_amount":transaction_amount,
            "closing_balance" : available_balance - transaction_amount,
            "status": "Pending"
        })
        txn_log.insert(ignore_permissions=True)

        # Create an order
        order = frappe.get_doc({
            "doctype": "Orders",
            "order_amount": order_amount,
            "product_name": product_name,
            "mobile_number": mobile_number,
            "processor": processor_name,
            "channel": "Android",
            "transaction_id":txn_log.name,
            "channel_partner": channel_partner,
            "order_status": "Pending"
        })
        order.insert(ignore_permissions=True)

        # Link Order ID in Transaction Log
        txn_log.order_id = order.name
        txn_log.save(ignore_permissions=True)

        
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
        response_data = response.json()
        if response_data["status"] == "success":
            # Create a final transaction log (Hold amount)
            txn_log.status = "Successful"
            txn_log.transaction_type = "Debit (Final)"
            txn_log.save(ignore_permissions=True)

            order.order_status="Success"
            order.save(ignore_permissions=True)

            frappe.db.commit()
            return {"status": "success", "transaction_id":txn_log.name}
        elif response_data["status"] == "pending":
            txn_log.save(ignore_permissions=True)
            frappe.db.commit()
            return {"status": "pending", "message": "Transaction processing", "order_id": order.name, "transaction_id": txn_log.name, "pay_id": response_data["payid"]}
        
        else:
            # Mark transaction as failed
            txn_log.status = "Failed"
            txn_log.transaction_type = "Credit Reversal"
            txn_log.closing_balance = available_balance + transaction_amount
            txn_log.save(ignore_permissions=True)
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
        transaction_id = data.get("transaction_id")

        if not order_id or not transaction_id:
            frappe.throw("Invalid webhook data: Missing Order ID or Transaction ID")

        # Fetch order and pending transaction log
        order = frappe.get_doc("Orders", order_id)
        
        if not order or order.order_status!="Pending":
            frappe.throw("No pending order found with this Order ID")

        txn_log = frappe.get_doc("Payment Transaction Logs",transaction_id)

        if not txn_log or txn_log.status!="Pending":
            frappe.throw("No pending txn found with this txn ID")

        previous_balance = txn_log.closing_balance  # Balance after hold

        if status.lower() == "success":
            # Finalize the transaction
            txn_log.status = "Successful"
            txn_log.transaction_type = "Debit (Final)"
            txn_log.save(ignore_permissions=True)

            order.order_status = "Successful"
            order.transaction_id=txn_log.name
            order.save(ignore_permissions=True)

        else:
            # Refund the amount back
            refunded_balance = previous_balance + txn_log.transaction_amount
            txn_log.status = "Failed"
            txn_log.transaction_type = "Credit Reversal"
            txn_log.closing_balance = refunded_balance
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

    # Get latest closing balance
    previous_balance = get_closing_balance(channel_partner)
    new_balance = previous_balance + amount

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
        "closing_balance":new_balance,
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

    frappe.db.commit()
    return transaction

def get_available_balance(channel_partner):
    """Calculate available balance based on transaction log."""
    total_credits = frappe.db.sql("""
        SELECT SUM(transaction_amount) FROM `tabPayment Transaction Logs`
        WHERE channel_partner = %s AND transaction_type IN ('Credit (Top-up)', 'Credit Reversal')
    """, (channel_partner))[0][0] or 0

    total_debits = frappe.db.sql("""
        SELECT SUM(transaction_amount) FROM `tabPayment Transaction Logs`
        WHERE channel_partner = %s AND transaction_type IN ('Debit (Hold)', 'Debit (Final)')
    """, (channel_partner))[0][0] or 0

    return total_credits - total_debits

def get_closing_balance(channel_partner):
    """Fetch the latest closing balance from the transaction log."""
    latest_balance = frappe.db.sql("""
        SELECT closing_balance FROM `tabPayment Transaction Logs`
        WHERE channel_partner = %s
        ORDER BY creation DESC
        LIMIT 1
    """, (channel_partner,))

    return latest_balance[0][0] if latest_balance else 0  # Default to 0 if no transactions exist


@frappe.whitelist()
def bulk_recharge():
    try:
        for i in range(1,1001):
            make_an_order("Airtel", "1", "Scriza", i, "7451973840", "Tata"):
    
    except Exception as e:
        frappe.log_error("Bulk Recharges falied",str(e))
        frappe.throw(str(e))
    
    return {"Reachage Successful"}  
        