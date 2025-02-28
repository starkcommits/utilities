import frappe

def get_channel_partner():
    try:
        user = frappe.session.user  # Get logged-in user
        if not user:
            return {"error": "You aren't logged in."}
            
        # Find the Channel Partner where the user exists in the child table
        channel_partner_name = frappe.db.get_value(
            "Team",  # This is the child table Doctype
            {"person_name": user},   # Filter using child table directly
            "parent"  # Parent field gives the Channel Partner linked to this entry
        )
        
        if not channel_partner_name:
            return {"error": "Your company is not registered"}
            
        # Get the full channel partner document
        channel_partner = frappe.get_doc("Channel Partner", channel_partner_name)
        
        if channel_partner.status == "Blocked":
            return {"error": "Your status is blocked. Please contact Administrator."}
        
        return {"channel_partner":channel_partner}

    except Exception as e:
        frappe.log_error("Error in fetching channel partner and product", str(e))
        return {"error": str(e)}