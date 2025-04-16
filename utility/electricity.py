import frappe
import requests
from . import channel_partner as cp
from . import processor as pcr
from . import product as pdt
from frappe import _

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
                "message":"Wallet is not active. Please contact admininstrator"
            }

        if wallet.pin != data.pin:
            return {
                "Your pin is incorrect. Enter your correct pin."
            }

        products = pdt.get_product(data.product_name,"Electricity")

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
                    return {"status": "success", "remark":"Transaction Successful", "product_name":product.name, "order_id":order.name,"pay_id": response_data["payid"],"created_on":order.creation}

                elif response_data["status"] == "pending":
                    frappe.db.commit()
                    return {"status": "pending", "remark": "Transaction processing", "product_name":product.name, "order_id":order.name,"pay_id": response_data["payid"],"created_on":order.creation}
                
                else:
                    order.order_status="Canceled"
                    order.save(ignore_permissions=True)

                    frappe.db.commit()
                    
                    return {"status": "failed", "remark": "Transaction failed","product_name":product.name, "order_id":order.name,"pay_id": response_data["payid"],"created_on":order.creation}

            else:
                frappe.log_error(f"Processor function '{processor_name}' not found", "Order Processing Error")
        return {
            "error":"Unable to proceed Bill payment. All processors are busy. Please try again."
        }

    except Exception as e:
        frappe.log_error("Error in processing bill payment",f"{str(e)}")
        return {"Error":f"{str(e)}"}

