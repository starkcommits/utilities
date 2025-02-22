import frappe
import requests
import time
import json
import random

from typing import Optional, Dict, Any

def document_verification(product, identity_number: str,processor,order,txn_log):
    method = None
    payload = None
    if product.name == "PanCard Detail Finder":
        doc = frappe.get_doc({
            'doctype':'PanCard Verification',
            'pan_card_number': identity_number
        })
        doc.insert()

        method = next((m for m in processor.api_methods if m.method_name == "Pan Card Verification"), None)

        if not method:
            raise frappe.ValidationError("Pan Card Verification method not found in processor configuration")
        
        payload = {
            "client_ref_num":doc.name,
            "pan":doc.pan_card_number
        }
    else :
        doc = frappe.get_doc({
            'doctype':'AahaarCard Verification',
            'aadhaar_card_number': identity_number
        })
        doc.insert()

        method = next((m for m in processor.api_methods if m.method_name == "Aadhaar Card Verification"), None)

        if not method:
            raise frappe.ValidationError("Aadhaar Card Verification method not found in processor configuration")
        
        payload = {
            "client_ref_num":doc.name,
            "aadhaar":doc.aadhaar_card_number
        }
    
    api_token = next((config.api_key for config in processor.api_config if config.key_name == "Authorization Key"), None)

    if not api_token:
        raise frappe.ValidationError("API Token not found in processor configuration")
    url = processor.base_url + method.method_end_point
    # headers = {"Content-Type": "application/json"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {api_token}"
    }
    try:
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        time.sleep(2)
        frappe.log_error(
            title="API Request Response",
            message=f"Request Body: {payload}, Response Body: {response.text}",
            reference_doctype="Orders",  # The related document type
            reference_name=order.name  # The related order ID
        )
        api_response = response.json()
        if api_response["http_response_code"] == 200:
            # Create a final transaction log (Hold amount)
            txn_log.status = "Completed"
            txn_log.transaction_type = "Debit (Final)"
            txn_log.save(ignore_permissions=True)

            order.order_status="Completed"
            order.save(ignore_permissions=True)

            if product.name == "PanCard Detail Finder":
                doc.request_id = api_response.get("request_id")
                doc.client_ref_id = api_response.get("client_ref_num")
                doc.pan_number = api_response.get("result", {}).get("pan")
                doc.pan_type = api_response.get("result", {}).get("pan_type")
                doc.aadhaar_number = api_response.get("result", {}).get("aadhaar_number")
                doc.aadhaar_linked = 1 if api_response.get("result", {}).get("aadhaar_linked") else 0
                doc.date_of_birth = frappe.utils.get_datetime_str(frappe.utils.get_datetime_str(api_response.get("result", {}).get("dob"))),
                doc.mobile_number = api_response.get("result", {}).get("mobile")
                doc.email_id = api_response.get("result", {}).get("email")
                doc.pan_status = api_response.get("result", {}).get("pan_status")
                doc.pan_allotment_date = frappe.utils.get_datetime_str(api_response.get("result", {}).get("pan_allotment_date")),
                doc.full_name = api_response.get("result", {}).get("fullname")
                doc.first_name = api_response.get("result", {}).get("first_name")
                doc.middle_name = api_response.get("result", {}).get("middle_name")
                doc.last_name = api_response.get("result", {}).get("last_name")
                doc.gender = api_response.get("result", {}).get("gender")
                doc.is_sole_proprietor = 1 if api_response.get("result", {}).get("is_sole_proprietor") == "Y" else 0
                doc.is_director = 1 if api_response.get("result", {}).get("is_director") == "Y" else 0
                doc.is_salaried = 1 if api_response.get("result", {}).get("is_salaried") == "Y" else 0
                
                # Address fields
                address = api_response.get("result", {}).get("address", {})
                doc.building_name = address.get("building_name")
                doc.locality = address.get("locality")
                doc.street_name = address.get("street_name")
                doc.city = address.get("city")
                doc.state = address.get("state")
                doc.country = address.get("country")
                doc.pin_code = address.get("pincode")

                doc.save(ignore_permissions=True)
            else: 
                doc.request_id = api_response.get("request_id")
                doc.aadhaar_age_band = api_response.get("result", {}).get("aadhaar_age_band")
                doc.aadhaar_state = api_response.get("result", {}).get("aadhaar_state")
                doc.aadhaar_gender = api_response.get("result", {}).get("aadhaar_gender")
                doc.aadhaar_phone = api_response.get("result", {}).get("aadhaar_phone")
                doc.aadhaar_result = api_response.get("result", {}).get("aadhaar_result")

                doc.save(ignore_permissions=True)
    
            frappe.db.commit()
            # Convert to dict and remove unwanted metadata fields
            response_data = doc.as_dict()
            doc_name = response_data.get("name")
            response_data['id'] = doc_name
            metadata_fields = [
                "name", "owner", "creation", "modified", "modified_by",
                "docstatus", "idx","doctype", "request_id"
            ]
    
            # Remove metadata fields
            for field in metadata_fields:
                response_data.pop(field, None)
            return response_data

        elif response_data["status"] == "pending":
            txn_log.save(ignore_permissions=True)
            frappe.db.commit()
            return {"status": "pending", "message": "Transaction processing", "order_id": order.name, "transaction_id": txn_log.name, "pay_id": response_data["payid"]}
        
        else:
            # Mark transaction as failed
            txn_log.status = "Reversed"
            txn_log.transaction_type = "Credit Reversal"
            txn_log.save(ignore_permissions=True)

            order.order_status="Canceled"
            order.save(ignore_permissions=True)

            frappe.db.commit()
            
            return {"status": "failed", "message": "Transaction failed"}

    except Exception as e:
        frappe.log_error(f"API Call Failed: {str(e)}", "API Integration")

@frappe.whitelist()
def make_an_order(product_name: str, identity_number: str, channel_partner: str, order_amount: float = 0):

    try:
        order_amount = float(order_amount)
        product = frappe.get_doc("Product",product_name)
        
        partner = frappe.get_doc("Channel Partner",channel_partner)
        if partner.status == "Blocked":
            return {
                "Your status is blocked. Please contact Administrator."
            }
        
        partner_wallets = frappe.get_all("Partner Wallet",
            filters={"channel_partner":channel_partner, "status":"Active"},
            fields=["name","balance","status"]
        )
        if not partner_wallets:
            return {
                "error":"You don't have any active wallet. Please activate one or create a new one."
            }

        partner_wallet=None
        for wallet in partner_wallets:
            product_categories = frappe.get_all(
                "Wallet Including Table",
                filters={"parent": wallet["name"],"product_category":product.category},
                fields=["product_category"]
            )
            if product_categories:
                partner_wallet=wallet
                break
        
        if not partner_wallet:
            return {
                "error" : "You don't have any wallet for ordering this product."
            }
        
        # Check Available Balance
        available_balance = partner_wallet.balance

        # Fetch Channel Partner Discount
        product_pricing = frappe.get_all(
            "Product Pricing",
            filters={"parent": channel_partner, "product_name": product.name},
            fields=["discount_type", "discount_amount","plateform_fee_type","plateform_fee","is_active"]
        )

        # Calculate transaction amount with discount
        transaction_amount = order_amount
        discount_value = 0
        discount_type = "None"

        plateform_fee_value = 0
        plateform_fee_type = "None"

        if product_pricing:
            product_price = product_pricing[0]

            discount_value = float(product_price.get("discount_amount", 0))
            discount_type = product_price.get("discount_type", "None")

            if discount_type == "Percentage":
                discount_value = order_amount * discount_value / 100
                transaction_amount = order_amount - discount_value
            elif discount_type == "Fixed":
                transaction_amount = order_amount - discount_value
            
            plateform_fee_value = float(product_price.get("plateform_fee", 0))
            plateform_fee_type = product_price.get("plateform_fee_type","None")

            if plateform_fee_type == "Percentage":
                plateform_fee_value = order_amount * plateform_fee_value / 100
                transaction_amount = transaction_amount + plateform_fee_value
            elif plateform_fee_type == "Fixed":
                transaction_amount = transaction_amount + plateform_fee_value
            
        else:
            return {
                "You didn't have this product in your list. Please add it to use services"
            }
        
        if available_balance < transaction_amount:
            return {
                "Title": "Insufficient Balance",
                "data": "Please recharge your wallet to make transactions."
            } 
        # Create an order
        order = frappe.get_doc({
            "doctype": "Orders",
            "order_amount": order_amount,
            "product_name": product_name,
            "identity_number": identity_number,
            "channel": "Android",
            "channel_partner": channel_partner,
            "order_status": "Created"
        })
        order.insert(ignore_permissions=True)

        txn_log = frappe.get_doc({
            "doctype": "Payment Transaction Logs",
            "channel_partner": channel_partner,
            "product_name":product.name,
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
        processors = frappe.get_all(
            "Processor Table",
            filters={"parent":product.name,"is_active":1},
            fields=["name","processor"]
        )
        processor = frappe.get_doc("Processor", processors[0].processor)

        order.processor = processor.name
        order.save(ignore_permissions=True)

        frappe.db.commit()
        
        if product.category == "Verification":
            return document_verification(product,identity_number,processor,order,txn_log)
        
        method = next((m for m in processor.api_methods if m.method_name == "Make Payment"), None)

        if not method:
            raise frappe.ValidationError("Make Payment method not found in processor configuration")

        url = processor.base_url + method.method_end_point
        api_token = next((config.api_key for config in processor.api_config if config.key_name == "API Token"), None)

        if not api_token:
            raise frappe.ValidationError("API Token not found in processor configuration")

        provider_id = next((provider.product_id for provider in processor.providers if provider.product_name == product.product_name), None)
        
        if not provider_id:
            return {
                "error":"Provider Id is not configured"
            }

        payload = {
            "api_token": api_token,
            "provider_id": provider_id,
            "amount": order_amount,
            "number": identity_number,
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

    partner_wallet = frappe.get_doc("Partner Wallet",{
        "channel_partner":channel_partner
    })

    if partner_wallet.status == "Freeze":
        return {
            "Title":"Wallet Frozen",
            "data":" Your wallet is frozen. Please activate to make transactions."
        }
    
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
        "status": "Completed"
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

