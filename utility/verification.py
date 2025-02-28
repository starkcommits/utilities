import frappe
import requests
import time
import json
import random
from . import channel_partner as cp
from . import product as pdt
from typing import Optional, Dict, Any

@frappe.whitelist()
def pan_card(product_name: str, identity_number: str):
    try:
        partner = cp.get_channel_partner()

        # Check if there's an error in the result
        if "error" in partner:
            return partner

        channel_partner = partner["channel_partner"]
        products = pdt.get_product(product_name, "Verification")

        if "error" in products:
            return products
        
        product = products["product"]
        
        # Send request to payment processor
        processors = frappe.get_all(
            "Processor Table",
            filters={"parent": product.name, "is_active": 1},
            fields=["name", "processor"]
        )
        
        if not processors:
            return {"error": "No active processor found for this product"}
            
        processor = frappe.get_doc("Processor", processors[0].processor)

        # Create an order
        order = frappe.get_doc({
            "doctype": "Orders",
            "order_amount": 0,
            "product_name": product.product_name,
            "identity_number": identity_number,
            "channel": "Android",
            "processor": processor.name,
            "channel_partner": channel_partner.name,
            "order_status": "Created"
        })

        order.insert(ignore_permissions=True)
        frappe.db.commit()
        
        doc = frappe.get_doc({
            'doctype': 'PanCard Verification',
            'pan_card_number': identity_number
        })
        doc.insert()
        frappe.db.commit()

        method = next((m for m in processor.api_methods if m.method_name == "Pan Card Verification"), None)

        if not method:
            raise frappe.ValidationError("Pan Card Verification method not found in processor configuration")
        
        api_token = next((config.api_key for config in processor.api_config if config.key_name == "Authorization Key"), None)

        # Missing API endpoint definition - adding it
        url = processor.base_url + method.method_end_point
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "client_ref_num": order.name,
            "pan": doc.pan_card_number
        }

        #response = frappe.make_post_request(url, data=payload, headers=headers)
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        frappe.log_error(
            title="API Request Response",
            message=f"Request Body: {payload}, Response Body: {response.text}",
            reference_doctype="Orders",
            reference_name=order.name
        )
        
        api_response = response.json()
        if api_response["http_response_code"] == 200:
            doc.request_id = api_response.get("request_id")
            doc.client_ref_id = api_response.get("client_ref_num")
            doc.pan_number = api_response.get("result", {}).get("pan")
            doc.pan_type = api_response.get("result", {}).get("pan_type")
            doc.aadhaar_number = api_response.get("result", {}).get("aadhaar_number")
            doc.aadhaar_linked = 1 if api_response.get("result", {}).get("aadhaar_linked") else 0
            
            # Fix the datetime conversion - remove the double conversion
            doc.date_of_birth = frappe.utils.get_datetime_str(api_response.get("result", {}).get("dob"))
            
            doc.mobile_number = api_response.get("result", {}).get("mobile")
            doc.email_id = api_response.get("result", {}).get("email")
            doc.pan_status = api_response.get("result", {}).get("pan_status")
            
            # Fix the datetime conversion - remove the trailing comma
            doc.pan_allotment_date = frappe.utils.get_datetime_str(api_response.get("result", {}).get("pan_allotment_date"))
            
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
            frappe.db.commit()

            order.order_status = "Completed"
            order.save(ignore_permissions=True)
            
            # Convert to dict and remove unwanted metadata fields
            response_data = doc.as_dict()
            doc_name = response_data.get("name")
            response_data['id'] = doc_name
            metadata_fields = [
                "name", "owner", "creation", "modified", "modified_by",
                "docstatus", "idx", "doctype", "request_id"
            ]
    
            # Remove metadata fields
            for field in metadata_fields:
                response_data.pop(field, None)
            return response_data
        else:
            return {
                "error": "Error in fetching api"
            }
        
    except Exception as e:
        frappe.log_error(f"Error in pan card api, {str(e)}")
        return {
            "Error": f"{str(e)}"
        }


@frappe.whitelist()
def aadhaar_card(product_name: str, identity_number: str):
    try:
        partner = cp.get_channel_partner()

        # Check if there's an error in the result
        if "error" in partner:
            return partner
        
        products = pdt.get_product(product_name, "Verification")

        if "error" in products:
            return products

        channel_partner = partner["channel_partner"]
        product = products["product"]

        # Send request to payment processor
        processors = frappe.get_all(
            "Processor Table",
            filters={"parent":product.name,"is_active":1},
            fields=["name","processor"]
        )
        processor = frappe.get_doc("Processor", processors[0].processor)

        # Create an order
        order = frappe.get_doc({
            "doctype": "Orders",
            "order_amount": 0,
            "product_name": product.product_name,
            "identity_number": identity_number,
            "channel": "Android",
            "processor":processor.name,
            "channel_partner": channel_partner.name,
            "order_status": "Created"
        })

        order.insert(ignore_permissions=True)
        frappe.db.commit()
        doc = frappe.get_doc({
            'doctype':'AahaarCard Verification',
            'aadhaar_card_number': identity_number
        })
        doc.insert()
        frappe.db.commit()

        method = next((m for m in processor.api_methods if m.method_name == "Aadhaar Card Verification"), None)

        if not method:
            raise frappe.ValidationError("Aadhar Card Verification method not found in processor configuration")
        
        api_token = next((config.api_key for config in processor.api_config if config.key_name == "Authorization Key"), None)


        url = processor.base_url + method.method_end_point

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "client_ref_num":order.name,
            "aadhar":doc.aadhaar_card_number
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        # response = frappe.make_post_request(url, data=payload, headers=headers)
        
        frappe.log_error(
            title="API Request Response",
            message=f"Request Body: {payload}, Response Body: {response.text}",
            reference_doctype="Orders",  # The related document type
            reference_name=order.name  # The related order ID
        )
        api_response = response.json()
        if  api_response["http_response_code"] == 200:
            doc.request_id = api_response.get("request_id")
            doc.aadhaar_age_band = api_response.get("result", {}).get("aadhaar_age_band")
            doc.aadhaar_state = api_response.get("result", {}).get("aadhaar_state")
            doc.aadhaar_gender = api_response.get("result", {}).get("aadhaar_gender")
            doc.aadhaar_phone = api_response.get("result", {}).get("aadhaar_phone")
            doc.aadhaar_result = api_response.get("result", {}).get("aadhaar_result")

            doc.save(ignore_permissions=True)
            frappe.db.commit()
            
            order.order_status="Completed"
            order.save(ignore_permissions=True)
            
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
            frappe.db.commit()
            return {"status": "pending", "message": "Transaction processing", "order_id": order.name, "pay_id": response_data["payid"]}
        
        else:
            order.order_status="Canceled"
            order.save(ignore_permissions=True)

            frappe.db.commit()
            
            return {"status": "failed", "message": "Transaction failed"}

    except Exception as e:
        frappe.log_error("Error",f"Error in Aadhaar API call {str(e)}")
        return {
            f"Error in api call {str(e)}"
        }
