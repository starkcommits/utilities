import frappe
import requests
import time
import json
import random
from typing import Optional, Dict, Any

def document_verification(product, identity_number: str, processor, order_id, txn_log_id):
    method = None
    payload = None
    doc_name = None
    
    if product.get("name") == "PanCard Detail Finder":
        # Insert PAN verification record
        doc_name = frappe.db.insert(
            doctype='PanCard Verification',
            pan_card_number=identity_number
        )
        
        method = frappe.db.get_value("API Methods", 
            {"parent": processor.get("name"), "method_name": "Pan Card Verification"},
            ["method_name", "method_end_point"], as_dict=True)
        
        if not method:
            raise frappe.ValidationError("Pan Card Verification method not found")
        
        payload = {
            "client_ref_num": order_id,
            "pan": identity_number
        }
    else:
        # Insert Aadhaar verification record
        doc_name = frappe.db.insert(
            doctype='AahaarCard Verification',
            aadhaar_card_number=identity_number
        )
        
        method = frappe.db.get_value("API Methods", 
            {"parent": processor.get("name"), "method_name": "Aadhaar Card Verification"},
            ["method_name", "method_end_point"], as_dict=True)
            
        if not method:
            raise frappe.ValidationError("Aadhaar Card Verification method not found")
        
        payload = {
            "client_ref_num": order_id,
            "aadhaar": identity_number
        }

    api_token = frappe.db.get_value("API Config", 
        {"parent": processor.get("name"), "key_name": "Authorization Key"}, 
        "api_key")

    url = processor.get("base_url") + method.get("method_end_point")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {api_token}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        frappe.log_error(
            title="API Request Response",
            message=f"Request Body: {payload}, Response Body: {response.text}",
            reference_doctype="Orders",
            reference_name=order_id
        )

        api_response = response.json()
        
        if api_response["http_response_code"] == 200:
            # Update transaction log
            frappe.db.set_value("Payment Transaction Logs", txn_log_id, {
                "status": "Completed",
                "transaction_type": "Debit (Final)"
            })

            # Update order status
            frappe.db.set_value("Orders", order_id, {
                "order_status": "Completed"
            })

            if product.get("name") == "PanCard Detail Finder":
                # Update PAN verification details
                update_data = {
                    "request_id": api_response.get("request_id"),
                    "client_ref_id": api_response.get("client_ref_num"),
                    "pan_number": api_response.get("result", {}).get("pan"),
                    "pan_type": api_response.get("result", {}).get("pan_type"),
                    "aadhaar_number": api_response.get("result", {}).get("aadhaar_number"),
                    "aadhaar_linked": 1 if api_response.get("result", {}).get("aadhaar_linked") else 0,
                    "date_of_birth": frappe.utils.get_datetime_str(api_response.get("result", {}).get("dob")),
                    "mobile_number": api_response.get("result", {}).get("mobile"),
                    "email_id": api_response.get("result", {}).get("email"),
                    "pan_status": api_response.get("result", {}).get("pan_status"),
                    "pan_allotment_date": frappe.utils.get_datetime_str(api_response.get("result", {}).get("pan_allotment_date")),
                    "full_name": api_response.get("result", {}).get("fullname"),
                    "first_name": api_response.get("result", {}).get("first_name"),
                    "middle_name": api_response.get("result", {}).get("middle_name"),
                    "last_name": api_response.get("result", {}).get("last_name"),
                    "gender": api_response.get("result", {}).get("gender"),
                    "is_sole_proprietor": 1 if api_response.get("result", {}).get("is_sole_proprietor") == "Y" else 0,
                    "is_director": 1 if api_response.get("result", {}).get("is_director") == "Y" else 0,
                    "is_salaried": 1 if api_response.get("result", {}).get("is_salaried") == "Y" else 0
                }

                # Add address fields
                address = api_response.get("result", {}).get("address", {})
                update_data.update({
                    "building_name": address.get("building_name"),
                    "locality": address.get("locality"),
                    "street_name": address.get("street_name"),
                    "city": address.get("city"),
                    "state": address.get("state"),
                    "country": address.get("country"),
                    "pin_code": address.get("pincode")
                })

                frappe.db.set_value("PanCard Verification", doc_name, update_data)
            else:
                # Update Aadhaar verification details
                frappe.db.set_value("AahaarCard Verification", doc_name, {
                    "request_id": api_response.get("request_id"),
                    "aadhaar_age_band": api_response.get("result", {}).get("aadhaar_age_band"),
                    "aadhaar_state": api_response.get("result", {}).get("aadhaar_state"),
                    "aadhaar_gender": api_response.get("result", {}).get("aadhaar_gender"),
                    "aadhaar_phone": api_response.get("result", {}).get("aadhaar_phone"),
                    "aadhaar_result": api_response.get("result", {}).get("aadhaar_result")
                })

            frappe.db.commit()
            
            # Get updated document data
            response_data = frappe.db.get_value(
                "PanCard Verification" if product.get("name") == "PanCard Detail Finder" else "AahaarCard Verification",
                doc_name, "*", as_dict=True
            )
            
            response_data['id'] = doc_name
            
            # Remove metadata fields
            metadata_fields = [
                "name", "owner", "creation", "modified", "modified_by",
                "docstatus", "idx", "doctype", "request_id"
            ]
            for field in metadata_fields:
                response_data.pop(field, None)
                
            return response_data

        elif api_response.get("status") == "pending":
            frappe.db.commit()
            return {
                "status": "pending",
                "message": "Transaction processing",
                "order_id": order_id,
                "transaction_id": txn_log_id,
                "pay_id": api_response.get("payid")
            }
        
        else:
            # Update transaction and order status for failure
            frappe.db.set_value("Payment Transaction Logs", txn_log_id, {
                "status": "Reversed",
                "transaction_type": "Credit Reversal"
            })

            frappe.db.set_value("Orders", order_id, {
                "order_status": "Canceled"
            })

            frappe.db.commit()
            return {"status": "failed", "message": "Transaction failed"}

    except Exception as e:
        frappe.log_error(f"API Call Failed: {str(e)}", "API Integration")
        raise

# @frappe.whitelist()
# def make_an_order(product_name: str, identity_number: str, channel_partner: str, order_amount: float = 0):
#     try:
#         order_amount = float(order_amount)
        
#         # Get product details
#         product = frappe.db.get_value("Product", product_name, "*", as_dict=True)
#         if not product:
#             return {"error": "Product not found"}

#         # Check partner status
#         partner_status = frappe.db.get_value("Channel Partner", channel_partner, "status")
#         if partner_status == "Blocked":
#             return {"error": "Your status is blocked. Please contact Administrator."}

#         # Get active wallets
#         partner_wallets = frappe.db.get_all("Partner Wallet",
#             filters={
#                 "channel_partner": channel_partner,
#                 "status": "Active"
#             },
#             fields=["name", "balance", "status"]
#         )

#         if not partner_wallets:
#             return {"error": "You don't have any active wallet. Please activate one or create a new one."}

#         # Find suitable wallet
#         partner_wallet = None
#         for wallet in partner_wallets:
#             product_categories = frappe.db.get_all(
#                 "Wallet Including Table",
#                 filters={
#                     "parent": wallet["name"],
#                     "product_category": product.get("category")
#                 },
#                 fields=["product_category"]
#             )
#             if product_categories:
#                 partner_wallet = wallet
#                 break

#         if not partner_wallet:
#             return {"error": "You don't have any wallet for ordering this product."}

#         # Get product pricing
#         product_pricing = frappe.db.get_value("Product Pricing",
#             {
#                 "parent": channel_partner,
#                 "product_name": product.get("name")
#             },
#             ["discount_type", "discount_amount", "plateform_fee_type", "plateform_fee"],
#             as_dict=True
#         )

#         if not product_pricing:
#             return {"error": "You didn't have this product in your list. Please add it to use services"}

#         # Calculate transaction amount
#         transaction_amount = order_amount
#         discount_value = float(product_pricing.get("discount_amount", 0))
#         discount_type = product_pricing.get("discount_type", "None")
        
#         if discount_type == "Percentage":
#             discount_value = order_amount * discount_value / 100
#             transaction_amount -= discount_value
#         elif discount_type == "Fixed":
#             transaction_amount -= discount_value

#         plateform_fee_value = float(product_pricing.get("plateform_fee", 0))
#         plateform_fee_type = product_pricing.get("plateform_fee_type", "None")

#         if plateform_fee_type == "Percentage":
#             plateform_fee_value = order_amount * plateform_fee_value / 100
#             transaction_amount += plateform_fee_value
#         elif plateform_fee_type == "Fixed":
#             transaction_amount += plateform_fee_value

#         # Check balance
#         if partner_wallet["balance"] < transaction_amount:
#             return {
#                 "Title": "Insufficient Balance",
#                 "data": "Please recharge your wallet to make transactions."
#             }

#         # Create order
#         order_id = frappe.db.insert(
#             doctype="Orders",
#             order_amount=order_amount,
#             product_name=product_name,
#             identity_number=identity_number,
#             channel="Android",
#             channel_partner=channel_partner,
#             order_status="Created"
#         )

#         # Create transaction log
#         txn_log_id = frappe.db.insert(
#             doctype="Payment Transaction Logs",
#             channel_partner=channel_partner,
#             product_name=product.get("name"),
#             order_id=order_id,
#             order_amount=order_amount,
#             discount=discount_value,
#             plateform_fee=plateform_fee_value,
#             transaction_type="Debit (Hold)",
#             transaction_amount=transaction_amount,
#             closing_balance=partner_wallet["balance"] - transaction_amount,
#             status="Created"
#         )

#         # Update order with transaction ID
#         frappe.db.set_value("Orders", order_id, "transaction_id", txn_log_id)

#         # Get processor
#         processor = frappe.db.get_value("Processor",
#             {"name": frappe.db.get_value("Processor Table", 
#                 {"parent": product.get("name"), "is_active": 1}, "processor")},
#             "*", as_dict=True
#         )

#         frappe.db.set_value("Orders", order_id, "processor", processor.get("name"))
        
#         frappe.db.commit()

#         if product.get("category") == "Verification":
#             return document_verification(product, identity_number, processor, order_id, txn_log_id)

#         # Rest of the payment processing logic...
#         # (Payment API calls and response handling remain the same)

#     except Exception as e:
#         frappe.log_error("Order Processing Error", str(e))
#         raise

@frappe.whitelist()
def make_an_order(product_name: str, identity_number: str, channel_partner: str, order_amount: float = 0):
    try:
        
        # Get product details
        product = frappe.db.get_value("Product", product_name, "*", as_dict=True)
        if not product:
            return {"error": "Product not found"}

        # Check partner status
        partner_status = frappe.db.get_value("Channel Partner", channel_partner, "status")
        if partner_status == "Blocked":
            return {"error": "Your status is blocked. Please contact Administrator."}

        # Get active wallets
        partner_wallets = frappe.db.get_all("Partner Wallet",
            filters={
                "channel_partner": channel_partner,
                "status": "Active"
            },
            fields=["name", "balance", "status"]
        )

        if not partner_wallets:
            return {"error": "You don't have any active wallet. Please activate one or create a new one."}

        # Find suitable wallet
        partner_wallet = None
        for wallet in partner_wallets:
            product_categories = frappe.db.get_all(
                "Wallet Including Table",
                filters={
                    "parent": wallet["name"],
                    "product_category": product.get("category")
                },
                fields=["product_category"]
            )
            if product_categories:
                partner_wallet = wallet
                break

        if not partner_wallet:
            return {"error": "You don't have any wallet for ordering this product."}

        # Get product pricing
        product_pricing = frappe.db.get_value("Product Pricing",
            {
                "parent": channel_partner,
                "product_name": product.get("name")
            },
            ["discount_type", "discount_amount", "plateform_fee_type", "plateform_fee"],
            as_dict=True
        )

        if not product_pricing:
            return {"error": "You didn't have this product in your list. Please add it to use services"}

        # Calculate transaction amount
        transaction_amount = order_amount
        discount_value = float(product_pricing.get("discount_amount", 0))
        discount_type = product_pricing.get("discount_type", "None")
        
        if discount_type == "Percentage":
            discount_value = order_amount * discount_value / 100
            transaction_amount -= discount_value
        elif discount_type == "Fixed":
            transaction_amount -= discount_value

        plateform_fee_value = float(product_pricing.get("plateform_fee", 0))
        plateform_fee_type = product_pricing.get("plateform_fee_type", "None")

        if plateform_fee_type == "Percentage":
            plateform_fee_value = order_amount * plateform_fee_value / 100
            transaction_amount += plateform_fee_value
        elif plateform_fee_type == "Fixed":
            transaction_amount += plateform_fee_value

        # Check balance
        if partner_wallet["balance"] < transaction_amount:
            return {
                "Title": "Insufficient Balance",
                "data": "Please recharge your wallet to make transactions."
            }
        
        order_amount = float(order_amount)
        # Generate a unique name for the order
        order_id = frappe.generate_hash("Orders", 10)  # Generates a unique hash
        
        # Create order using SQL with name field
        frappe.db.sql("""
            INSERT INTO `tabOrders` 
            (name, order_amount, product_name, identity_number, channel, 
            channel_partner, order_status, owner, modified_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            order_id,
            order_amount, 
            product_name, 
            identity_number, 
            "Android", 
            channel_partner, 
            "Created",
            frappe.session.user,  # Current user as owner
            frappe.session.user   # Current user as modifier
        ))
        
        frappe.db.commit()

        # Generate unique transaction log ID
        txn_log_id = frappe.generate_hash("Payment Transaction Logs", 10)

        # Create transaction log with name field
        txn_log_query = """
            INSERT INTO `tabPayment Transaction Logs`
            (name, channel_partner, product_name, order_id, order_amount, 
            discount, plateform_fee, transaction_type, transaction_amount, 
            closing_balance, status, owner, modified_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        frappe.db.sql(txn_log_query, (
            txn_log_id,
            channel_partner,
            product_name,
            order_id,
            order_amount,
            discount_value,
            plateform_fee_value,
            "Debit (Hold)",
            transaction_amount,
            partner_wallet["balance"] - transaction_amount,
            "Created",
            frappe.session.user,
            frappe.session.user
        ))
        
        frappe.db.commit()

        # Update order with transaction ID
        frappe.db.sql("""
            UPDATE `tabOrders`
            SET transaction_id = %s,
                modified = NOW(),
                modified_by = %s
            WHERE name = %s
        """, (txn_log_id, frappe.session.user, order_id))

        # Get processor details and update order
        processor_name = frappe.db.get_value("Processor Table", 
            {"parent": product_name, "is_active": 1}, 
            "processor"
        )
        
        if processor_name:
            frappe.db.sql("""
                UPDATE `tabOrders`
                SET processor = %s,
                    modified = NOW(),
                    modified_by = %s
                WHERE name = %s
            """, (processor_name, frappe.session.user, order_id))
        
        frappe.db.commit()

        if product.get("category") == "Verification":
            return document_verification(product, identity_number, processor, order_id, txn_log_id)

        # Continue with rest of the logic...
        return {
            "status": "success",
            "order_id": order_id,
            "transaction_id": txn_log_id
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Order Processing Error", str(e))
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def topup(amount, channel_partner):
    try:
        amount = float(amount)

        # Check wallet status
        wallet_status = frappe.db.get_value("Partner Wallet", 
            {"channel_partner": channel_partner}, "status")
        
        if wallet_status == "Freeze":
            return {
                "Title": "Wallet Frozen",
                "data": "Your wallet is frozen. Please activate to make transactions."
            }

        # Create order
        order_id = frappe.db.insert(
            doctype="Orders",
            product_name="Wallet Top Up",
            order_amount=amount,
            channel_partner=channel_partner,
            channel="Web",
            order_status="Created"
        )

        # Create transaction
        txn_id = frappe.db.insert(
            doctype="Payment Transaction Logs",
            source_docname="Orders",
            order_id=order_id,
            channel_partner=channel_partner,
            channel="Web",
            product_name="Wallet Top Up",
            order_amount=amount,
            transaction_amount=amount,
            discount=0,
            transaction_type="Credit (Top-up)",
            status="Completed"
        )

        # Update order
        frappe.db.set_value("Orders", order_id, {
            "order_status": "Completed",
            "transaction_id": txn_id,
            "order_remark": "Wallet recharged successfully"
        })

        frappe.db.commit()
        return {"message": "Wallet recharged successfully"}

    except Exception as e:
        frappe.log_error("Topup Error", str(e))
        raise

@frappe.whitelist()
def delete_record():
    try:
        # First update foreign key references to null
        frappe.db.sql("""
            UPDATE `tabOrders` SET transaction_id = NULL
        """)
        
        frappe.db.sql("""
            UPDATE `tabPayment Transaction Logs` SET order_id = NULL
        """)

        frappe.db.commit()

        # Then delete records
        frappe.db.sql("""
            DELETE FROM `tabPayment Transaction Logs`
        """)
        
        frappe.db.sql("""
            DELETE FROM `tabOrders`
        """)

        frappe.db.commit()
        return {"message": "Records deleted successfully"}

    except Exception as e:
        frappe.log_error("Delete Records Error", str(e))
        raise