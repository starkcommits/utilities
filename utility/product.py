import frappe

def get_product(product_name:str, category: str):
    if not product_name:
        return {
            "Product name is missing."
        }
    
    if not category:
        return {
            "Category is missing."
        }
    
    # Get the full product document
    product = frappe.get_doc(
        "Product",
        {"product_name": product_name, "category": category}
    )

    if not product:
        return {"error": f"There is no such product in {category} category"}
    
    return {"product": product}