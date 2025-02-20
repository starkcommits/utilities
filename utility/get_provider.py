import frappe
import requests

@frappe.whitelist()
def get_provider_detail(product_name):
    # Get processor document
    processor = frappe.get_doc(
        "Processor",
        {"processor_name": "Scriza"}
    )
    
    # Find the correct method from api_methods
    method = next(
        (m for m in processor.api_methods if m.method_name == "Get Provider"),
        None
    )
    
    if not method:
        frappe.throw("Get Provider method not found in processor configuration")
    
    # Construct URL
    url = processor.base_url + method.method_end_point
    
    # Get API token
    api_token = next(
        (config.api_key for config in processor.api_config if config.key_name == "API Token"),
        None
    )
    
    if not api_token:
        frappe.throw("API Token not found in processor configuration")
    
    payload = {
        "api_token": api_token
    }
    
    try:
        # Make API request
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            api_data = response.json()
            
            if api_data.get("status") != "success":
                frappe.throw("API returned unsuccessful status")
            
            # Get all products from your system
            products = frappe.get_all(
                "Product",
                fields=["product_name"]
            )
            
            # Clear existing providers
            processor.providers = []
            
            # Match products with API providers and update
            for provider in api_data.get("providers", []):
                # Check if this provider matches any of our products
                if any(p.product_name.lower() == provider["provider_name"].lower() for p in products):
                    # Add to providers child table
                    processor.append("providers", {
                        "product_name": provider["provider_name"],
                        "product_id": provider["provider_id"],
                        "service_name": provider["service_name"],
                        "service_id": provider["service_id"],
                        "is_active": 1
                    })
            
            # Save the processor document
            processor.save()
            frappe.db.commit()
            
            # Return specific provider details if requested
            if product_name:
                return next(
                    (provider for provider in processor.providers 
                    if provider.product_name.lower() == product_name.lower()),
                    None
                )
            
            return {"message": "Providers updated successfully"}
            
        else:
            frappe.throw(f"API request failed with status code: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        frappe.throw(f"API request failed: {str(e)}")
    except Exception as e:
        frappe.throw(f"Unexpected error: {str(e)}")