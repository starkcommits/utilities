import frappe
import json
from frappe import _
from typing import Optional, Dict, Any
import requests
from . import channel_partner as cp
from . import processor as pcr
from . import product as pdt


@frappe.whitelist(allow_guest=True)
def get_product(product_name):
    try:

        """Fetch product details without unnecessary metadata"""
        product = frappe.get_doc("Product", product_name)

        # Extract required fields
        response = {
            "product_name": product.product_name,
            "icon": product.icon,
            "category": product.category,
            "bbps_config": []
        }

        # Extract child table data (bbps_config)
        for config in product.bbps_config:
            response["bbps_config"].append({
                "config_name": config.config_name,
                "config_value": config.config_value,
                "remark": config.remark
            })

        return response
    except Exception as e:
        frappe.log_error("Error in fetching product",f"{str(e)}")
        return {
            "status":"error",
            "message":f"Error in fetching {product_name} detail"
        }



@frappe.whitelist(allow_guest=True)
def verify_bill():
    try:
        data = frappe._dict(frappe.request.get_json())
        if not data:
            return {
                "status":"error",
                "message":"Please send required fields"
            }
        
        # Get processor document
        processor = frappe.get_doc(
            "Processor",
            {"processor_name": "Scriza"}
        )
        
        # Find the correct method from api_methods
        method = next(
            (m for m in processor.api_methods if m.method_name == "Bill Verify"),
            None
        )
        
        if not method:
            frappe.throw("Bill Verify method not found in processor configuration")
        
        # Construct URL
        url = processor.base_url + method.method_end_point
        
        # Get API token
        api_token = next(
            (config.api_key for config in processor.api_config if config.key_name == "API Token"),
            None
        )
        
        if not api_token:
            frappe.throw("API Token not found in processor configuration")
        
        provider_id = frappe.db.get_value(
            "Provider Detail",
            {"product_name":data.product_name},
            "product_id"
        )

        payload = {
            "api_token": api_token,
            "provider_id": provider_id,
            "optional1": data.optional1
        }

        if data.optional2:
            payload["optional2"]=data.optional2
        if data.optional3:
            payload["optional3"]=data.optional3

        try:
            # Make API request
            frappe.log_error("Bill Verify",f"url:{url}, payload:{payload}")
            
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "message":"Error in bill verification data fetching"
                }
        
        except Exception as e:
            frappe.log_error("Error in making bill verify api call",f"{str(e)}")
            return {"Error":f"{str(e)}"}

    except Exception as e:
        frappe.log_error("Error in bill verification process",f"{str(e)}")
        return {"Error":f"{str(e)}"}


@frappe.whitelist(allow_guest=True)
def order():
    try:
        data = frappe._dict(frappe.request.get_json())
        if not data:
            return {
                "status":"error",
                "message":"Please send required fields"
            }
        
        partner = frappe.get_doc("Channel Partner",data.user_email)

        if not partner:
            return {
                "error":"You are not a registered user. Please do registration first."
            }
        
        wallet = frappe.get_doc("Partner Wallet",partner.name)
        
        if wallet.status !="Active":
            return {
                "message":"Your wallet is not active. Please contact admininstrator"
            }

        if wallet.pin != data.pin:
            return {
                "Your pin is incorrect. Enter your correct pin."
            }
        
        products = pdt.get_product(data.product_name,data.category)

        if "error" in products:
            return products
        
        product = products["product"]

        # Create an order
        order = frappe.get_doc({
            "doctype": "Orders",
            "order_amount": data.order_amount,
            "product_name": data.product_name,
            "identity_number": data.identity_number,
            "channel": "Android",
            "channel_partner": partner.name,
            "order_status": "Created"
        })
        order.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Send request to payment processor
        processors = frappe.get_all(
            "Processor Table",
            filters={"parent":product.name,"is_active":1},
            fields=["name","processor"]
        )
        

        for temp in processors:
            processor_name = temp["processor"]  # Get processor function name as a string

            # Dynamically get the function from the processor module
            processor_function = getattr(pcr, processor_name, None)

            if processor_function and callable(processor_function):
                result = processor_function(order)  # Call the function dynamically
                processor = result["processor"]
                payload2 = result["payload"]
                headers = result["headers"]
                
                payload = {
                    "api_token": payload2["api_token"],
                    "provider_id": payload2["provider_id"],
                    "amount": order.order_amount,
                    "optional1": data.identity_number,
                    "client_id": order.name,
                    "environment": "UAT"
                }
                if data.optional2:
                    payload["optional2"]=data.optional2

                if data.optional3:
                    payload["optional3"]=data.optional3

                if data.optional4:
                    payload["optional4"]=data.optional4
                    
                order.processor = processor.name
                order.save(ignore_permissions=True)

                method = frappe.db.get_value(
                    "API Methods",
                    {"method_name":"Make Payment"}, 
                    "method_end_point"
                )
                if not method :
                    frappe.throw(f"{processor.name} doesn't have make payment method")
                    continue
                
                url = processor.base_url + method
            
                response = requests.get(url, params=payload)
                # response = frappe.make_get_request(url, headers = headers, params = payload)
                frappe.log_error(
                    title="API Request Response",
                    message=f"Request Body: {payload}, Response Body: {response.text}",
                    reference_doctype="Orders",  # The related document type
                    reference_name=order.name  # The related order ID
                )

                response_data = response.json()
                if response_data["status"] == "success":
                    order.order_status="Completed"
                    order.save(ignore_permissions=True)

                    frappe.db.commit()
                    return {"status": "success", "message":'Transaction Successful',"order_id":order.name, "pay_id":response_data["pay_id"]}

                elif response_data["status"] == "pending":
                    frappe.db.commit()
                    return {"status": "pending", "message": "Transaction processing", "order_id": order.name, "pay_id": response_data["payid"]}
                
                else:
                    order.order_status="Canceled"
                    order.save(ignore_permissions=True)

                    frappe.db.commit()
                    
                    return {"status": "failed", "message": "Transaction failed"}

            else:
                frappe.log_error(f"Processor function '{processor_name}' not found", "Order Processing Error")
        return {
            "error":"Unable to proceed Bill payment. All processors are busy. Please try again."
        }

    except Exception as e:
        frappe.log_error("Error in processing bill payment",f"{str(e)}")
        return {"Error":f"{str(e)}"}



@frappe.whitelist()
def import_electricity_providers():
    try:
        # Get JSON data from the request
        data = frappe.request.get_json()
        
        # Ensure data is a list
        if not isinstance(data, list):
            frappe.throw(_("Invalid data format. Expected a list of providers."))

        for provider in data:
            # Create a new Electricity Provider document
            doc = frappe.get_doc({
                "doctype": "Product",
                "product_name": provider.get("provider_name"),  # Mapping Product Name to Provider Name
                "category": "FasTag Bill",  # Mapping Category to Service Name
                "icon": provider.get("provider_icon"),  # Mapping Icon to Provider Icon
                "partial_payment_allowed": provider.get("partial_payment_allowed"),
                "is_active": 1,
                "bbps_config": []  # Initialize child table
            })

            doc.append("processors",{
                "processor":"Scriza"
            })
            
            # Process Validators (BBPS Config Child Table)
            for validator in provider.get("validators", []):
                doc.append("bbps_config", {
                    "config_name": validator.get("name"),  # Mapping name → config_name
                    "config_value": validator.get("regex"),  # Mapping regex → config_value
                    "remark": validator.get("message"),  # Mapping message → remark
                    "required": validator.get("required")
                })

            # Insert or update the document
            try:
                doc.insert(ignore_permissions=True)  # Insert into Frappe DB
                frappe.db.commit()
                frappe.logger().info(f"Successfully inserted: {doc.product_name}")
            except frappe.DuplicateEntryError:
                frappe.logger().warning(f"Skipping duplicate: {doc.product_name}")
            except Exception as e:
                frappe.logger().error(f"Error inserting {doc.product_name}: {str(e)}")

        return {"status": "success", "message": "Electricity providers imported successfully."}
    
    except Exception as e:
        frappe.logger().error(f"Error in import_electricity_providers: {str(e)}")
        frappe.throw(_("Failed to import providers. Error: {0}").format(str(e)))
