import frappe
import requests

def make_an_order(doc, method):
    """
    Process an order by creating payment transaction logs and applying discounts.
    
    Args:
        doc: The order document
        method: The trigger method
    """
    try:
        # 🔹 Fetch Channel Partner Discount for the Ordered Product
        discount_details = frappe.get_all(
            "Product Pricing",
            filters={"parent": doc.channel_partner, "product_name": doc.product_name},
            fields=["discount_type", "discount_amount"]
        )

        # Default Transaction Amount is Order Amount
        transaction_amount = doc.order_amount
        discount_value = 0  # Default discount value
        discount_type = "None"

        if discount_details:
            discount = discount_details[0]  # Get the first matched record
            discount_value = discount["discount_amount"]
            discount_type = discount["discount_type"]

            # 🔹 Apply discount calculation
            if discount_type == "Percentage":
                transaction_amount = doc.order_amount - (doc.order_amount * (float(discount_value) / 100))
            elif discount_type == "Fixed":
                transaction_amount = doc.order_amount - float(discount_value)

        frappe.logger().info(f"💰 Calculated Transaction Amount for Order {doc.name}: {transaction_amount}")

        # 🔹 Create Payment Transaction Log
        transaction_log = frappe.get_doc({
            "doctype": "Payment Transaction Logs",
            "source_docname": doc.name,
            "order_id": doc.name,
            "channel_partner": doc.channel_partner,
            "channel": doc.channel,
            "product_name": doc.product_name,
            "order_amount": doc.order_amount,
            "transaction_amount": transaction_amount,  # Updated value
            "status": doc.order_status,
            "discount": discount_value
        })

        transaction_log.insert(ignore_permissions=True)  # Insert transaction log
        frappe.db.commit()
        
        # 🔹 Fetch the generated transaction ID
        transaction_id = transaction_log.name  # Ensure we have the created transaction log ID
        
        frappe.logger().info(f"✅ Transaction Log Created for Order {doc.name}: {transaction_id}")

        # 🔹 Update `transaction_id` in Orders
        doc.transaction_id = transaction_id
        doc.order_status = "Successful"
        doc.order_remark = "Order created successfully"
        doc.save(ignore_permissions=True)
        frappe.db.commit()  # Ensure update is saved

        frappe.logger().info(f"🔄 Successfully Updated Transaction ID in Order {doc.name}: {transaction_id}")

        # 🔹 Create a Comment in the Order Document
        comment_text = f"""
        🌐 **Order Processed Successfully**
        
        ✅ **Transaction Log Created**
        💰 **Order Amount:** {doc.order_amount}
        🎯 **Transaction Amount:** {transaction_amount}
        🏷️ **Discount Applied:** {discount_value} ({discount_type})
        🔄 **Status:** {doc.order_status}
        🔗 **Transaction ID:** {transaction_id}
        """

        comment_doc = frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Comment",
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "content": comment_text
        })

        comment_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.logger().info(f"💬 Comment Added to Order {doc.name}")

    except Exception as e:
        frappe.log_error(f"🔥 Failed during Transaction Processing: {str(e)}")