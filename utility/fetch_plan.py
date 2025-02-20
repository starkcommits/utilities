import frappe
import requests

@frappe.whitelist()
def get_plans(processor_name,provider_id,product_name):
    processor = frappe.get_doc(
        "Processor",
        {"processor_name":processor_name}
    )
    method = next(
        (m for m in processor.api_methods if m.method_name == "Prepaid Plan"),
        None
    )
    
    if not method:
        frappe.throw("Prepaid Plan method not found in processor configuration")
    
    url = processor.base_url + method.method_end_point
    
    # Get API token
    api_token = next(
        (config.api_key for config in processor.api_config if config.key_name == "API Token"),
        None
    )
    
    if not api_token:
        frappe.throw("API Token not found in processor configuration")
    
    payload = {
        "api_token": api_token,
        "provider_id":provider_id,
        "state_id":1
    }

    try:
        # Make API request
        # response = requests.post(url, json=payload, timeout=30)
        # if response.status_code == 200:
        #     api_data = response.json()
            
        #     if api_data.get("status") != "success":
        #         frappe.throw("API returned unsuccessful status")
            
            # Get existing plans
            existing_plans = frappe.get_all(
                "Plans",
                filters={"operator": product_name},
                fields=["name", "amount", "validity", "plan_category", "benefits"]
            )
            
            # # Get API plan amounts
            # api_plan_amounts = [plan["rs"] for plan in api_data.get("plans", [])]
            
            # # Filter existing plans that match API plan amounts
            # matching_plans = [
            #     plan for plan in existing_plans 
            #     if plan.amount in api_plan_amounts
            # ]
            
            return {
                "plans": existing_plans
            }

            
        else:
            frappe.throw(f"API request failed with status code: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        frappe.throw(f"API request failed: {str(e)}")
    except Exception as e:
        frappe.throw(f"Unexpected error: {str(e)}")
