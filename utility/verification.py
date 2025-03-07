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

@frappe.whitelist()
def gst(product_name: str, identity_number: str):
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
            'doctype':'GST Verification',
            'gstin_number': identity_number
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        method = next((m for m in processor.api_methods if m.method_name == "GST Verification"), None)

        if not method:
            raise frappe.ValidationError("GST Verification method not found in processor configuration")
        
        api_token = next((config.api_key for config in processor.api_config if config.key_name == "Authorization Key"), None)


        url = processor.base_url + method.method_end_point
        
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "gstin":doc.gstin_number
        }

        response = requests.get(url, params=payload, headers=headers)
        # response = frappe.make_post_request(url, data=payload, headers=headers)
        
        frappe.log_error(
            title="API Request Response",
            message=f"Request Body: {payload}, Response Body: {response.text}",
            reference_doctype="Orders",  # The related document type
            reference_name=order.name  # The related order ID
        )
        api_response = response.json()
        if api_response:

            taxpayer_details = api_response

            # Update GST Verification document
            doc.update({
                "gstin_number": taxpayer_details.get("gstin"),
                "legal_name": taxpayer_details.get("lgnm"),
                "trade_name": taxpayer_details.get("tradeNam"),
                "constitution_of_business": taxpayer_details.get("ctb"),
                "taxpayer_type": taxpayer_details.get("dty"),
                "registration_date": taxpayer_details.get("rgdt"),
                "status": taxpayer_details.get("sts"),
                "cancellation_date": taxpayer_details.get("cxdt"),
                "state_jurisdiction": taxpayer_details.get("stj"),
                "state_jurisdiction_code": taxpayer_details.get("stjCd"),
                "central_jurisdiction": taxpayer_details.get("ctj"),
                "central_jurisdiction_code": taxpayer_details.get("ctjCd")
                # "nature_of_business": ", ".join(taxpayer_details.get("nba", []))
            })
            
            for activity in taxpayer_details.get("nba", []):
                doc.append("business_activities", {
                    "activity": activity
                })
            
            for activity in taxpayer_details.get("adadr", []):
                address = activity.get("addr", {})
                # ntr = activity["ntr"]

                doc.append("addresses", {
                    "building_name": address.get("bnm"),
                    "street": address.get("st"),
                    "location": address.get("loc"),
                    "building_number": address.get("bno"),
                    "state_code": address.get("stcd"),
                    "floor_number": address.get("flno"),
                    "latitude": address.get("lt"),
                    "longitude": address.get("lg"),
                    "district": address.get("dst"),
                    "city": address.get("city"),
                    "pincode": address.get("pncd")
                    # "nature_of_address":ntr
                })


            doc.append("addresses", {
                "building_name": taxpayer_details.get("pradr", {}).get("bnm"),
                "street": taxpayer_details.get("pradr", {}).get("st"),
                "location": taxpayer_details.get("pradr", {}).get("loc"),
                "building_number": taxpayer_details.get("pradr", {}).get("bno"),
                "state_code": taxpayer_details.get("pradr", {}).get("stcd"),
                "floor_number": taxpayer_details.get("pradr", {}).get("flno"),
                "latitude": taxpayer_details.get("pradr", {}).get("lt"),
                "longitude": taxpayer_details.get("pradr", {}).get("lg"),
                "district": taxpayer_details.get("pradr", {}).get("dst"),
                "city": taxpayer_details.get("pradr", {}).get("city"),
                "pincode": taxpayer_details.get("pradr", {}).get("pncd")
                # "nature_of_address": ntr
            })

            doc.save(ignore_permissions=True)
            frappe.db.commit()
            
            order.order_status="Completed"
            order.save(ignore_permissions=True)

            return {"status": "success", "message": "GST Verification updated successfully", "docname": doc.name}

        return {"status": "error", "message": "Failed to fetch GST details", "response": api_response}
    
    except Exception as e:
        frappe.log_error("Error in GST Verification",f"{str(e)}")
        return {
            "Error":f"{str(e)}"
        }

@frappe.whitelist()
def mca(product_name: str, identity_number: str):
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
            'doctype':'MCA Verification',
            'cin_number': identity_number
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        method = next((m for m in processor.api_methods if m.method_name == "CIN Verification"), None)

        if not method:
            raise frappe.ValidationError("CIN Verification method not found in processor configuration")
        
        api_token = next((config.api_key for config in processor.api_config if config.key_name == "Authorization Key"), None)


        url = processor.base_url + method.method_end_point
        
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "cin":doc.cin_number
        }

        response = requests.get(url, params=payload, headers=headers)
        # response = frappe.make_post_request(url, data=payload, headers=headers)
        
        frappe.log_error(
            title="API Request Response",
            message=f"Request Body: {payload}, Response Body: {response.text}",
            reference_doctype="Orders",  # The related document type
            reference_name=order.name  # The related order ID
        )
        api_response = response.json()
        if not api_response:
            return {"status": "error", "message": "Failed to fetch MCA details"}

        # Map API response to the DocType fields
        doc.company_name = api_response.get("Company Name", "")
        doc.status = api_response.get("Status", "")
        doc.incorporation_date = api_response.get("Incorporation Date", "")
        doc.state = api_response.get("State", "")
        doc.roc = api_response.get("ROC", "")
        doc.last_balance_sheet = api_response.get("Last Balance Sheet", "")
        doc.last_agm = api_response.get("Last AGM", "")
        doc.paid_up_capital = api_response.get("Paid Up Capital", "")
        doc.authorized_capital = api_response.get("Authorized Capital", "")

        # Clear existing child table entries before inserting new ones
        doc.set("current_directors", [])
        doc.set("past_directors", [])
        doc.set("patents", [])
        doc.set("trademarks", [])
        doc.set("documents", [])

        # Populate Current Directors
        for director in api_response.get("Current Directors", []):
            doc.append("current_directors", {
                "director_name": director.get("Name", ""),
                "role": director.get("Role", ""),
                "position_duration": director.get("Position Duration", "")
            })

        # Populate Past Directors
        for director in api_response.get("Past Directors", []):
            doc.append("past_directors", {
                "director_name": director.get("Name", ""),
                "role": director.get("Role", ""),
                "position_duration": director.get("Position Duration", "")
            })

        # Populate Patents
        for patent in api_response.get("Patents", []):
            doc.append("patents", {
                "title": patent.get("Title", ""),
                "id": patent.get("ID", ""),
                "date": patent.get("Date", ""),
                "status": patent.get("Status", ""),
                "description": patent.get("Description", "")
            })

        # Populate Trademarks
        for trademark in api_response.get("Trademarks", []):
            doc.append("trademark", {
                "trademark_name": trademark.get("Name", ""),
                "id": trademark.get("ID", ""),
                "date": trademark.get("Date", ""),
                "status": trademark.get("Status", ""),
                "class": trademark.get("Class", ""),
                "description": trademark.get("Description", "")
            })

        # Populate Documents
        for document in api_response.get("Documents", []):
            doc.append("documents", {
                "document_name": document.get("Name", ""),
                "type": document.get("Type", ""),
                "date": document.get("Date", "")
            })

        doc.save(ignore_permissions=True)
        frappe.db.commit()

        order.order_status="Completed"
        order.save(ignore_permissions=True)

        return {"status": "success", "message": "CIN Verification updated successfully", "docname": doc.name}
    
    except Exception as e:
        frappe.log_error("Error in GST Verification",f"{str(e)}")
        return {
            "Error":f"{str(e)}"
        }