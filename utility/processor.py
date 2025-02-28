import frappe

def Scriza(order):

    processor = frappe.get_doc("Processor", "Scriza")

    # api_token = next((config.api_key for config in processor.api_config if config.key_name == "API Token"), None)
    api_token = frappe.db.get_value(
        "API Url",
        {"key_name":"API Token"},
        "api_key"
    )

    if not api_token:
        raise frappe.ValidationError("API Token not found in processor configuration")

    # provider_id = next((provider.product_id for provider in processor.providers if provider.product_name == order.product_name), None)
    
    provider_id = frappe.db.get_value(
        "Provider Detail",
        {"product_name":order.product_name},
        "product_id"
    )

    if not provider_id:
        return {
            "error":"Provider Id is not configured"
        }

    payload = {
        "api_token": api_token,
        "provider_id": provider_id,
        "amount": order.order_amount,
        "number": order.identity_number,
        "client_id": order.name,
        "environment": "UAT"
    }

    return {
        "processor": processor,
        "payload": payload,
        "headers": None
    }

def N8N(order):
    processor = frappe.get_doc("Processor", "N8N")

    

