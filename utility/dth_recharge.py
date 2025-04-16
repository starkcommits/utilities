import frappe
import requests
from . import channel_partner as cp
from . import processor as pcr
from . import product as pdt

@frappe.whitelist()
def order(user_email: str, product_name: str, identity_number: str, pin : int, order_amount: float = 0):
    try:
        partner = frappe.get_doc("Channel Partner",user_email)

        if not partner:
            return {
                "error":"You are not a registered user. Please do registration first."
            }
        
        wallet = frappe.get_doc("Partner Wallet",partner.name)

        if wallet.status !="Active":
            return {
                "message":"Your wallet is not active. Please contact admininstrator"
            }

        if wallet.pin !=pin:
            return {
                "Your pin is incorrect. Enter your correct pin."
            }

        products = pdt.get_product(product_name,"DTH Recharge")

        if "error" in products:
            return products
        
        product = products["product"]

        # Create an order
        order = frappe.get_doc({
            "doctype": "Orders",
            "order_amount": order_amount,
            "product_name": product_name,
            "identity_number": identity_number,
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
                payload = result["payload"]
                headers = result["headers"]

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
                    return {"status": "success", "remark":"Transaction Successful","product_name":product.name, "order_id":order.name,"pay_id": response_data["payid"],"created_on":order.creation}
                elif response_data["status"] == "pending":
                    frappe.db.commit()
                    return {"status": "pending", "remark": "Transaction processing", "order_id": order.name, "pay_id": response_data["payid"]}
                
                else:
                    order.order_status="Canceled"
                    order.save(ignore_permissions=True)

                    frappe.db.commit()
                    
                    return {"status": "failed", "message": "Transaction failed"}

            else:
                frappe.log_error(f"Processor function '{processor_name}' not found", "Order Processing Error")
        return {
            "error":"Unable to proceed DTH recharge. All processors are busy. Please try again."
        }

    except Exception as e:
        frappe.log_error("Error in DTH recharge processing",f"{str(e)}")
        return {"Error":f"{str(e)}"}
