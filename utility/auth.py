import frappe
from frappe.auth import LoginManager
from frappe import _
from frappe.utils.password import check_password
from frappe.utils import validate_email_address, getdate, today, get_formatted_email
import re

@frappe.whitelist(allow_guest=True)
def custom_login():
    # Parse login credentials
    usr = frappe.form_dict.get("usr")
    pwd = frappe.form_dict.get("pwd")

    if not usr or not pwd:
        frappe.throw(_("Missing login credentials"))

    # frappe.log_error("Credentials",f"{usr}:{pwd}")
    # Try to map mobile number to email
    if usr and usr.isnumeric():  # crude mobile check
        email = frappe.db.get_value("User", {"mobile_no": usr}, "name")
        if not email:
            return {
                "error":"No user found with this mobile number."
            }
        else:
            usr=email
    # frappe.log_error("Credentials",f"{usr}:{pwd}")
    # Authenticate
    login_manager = LoginManager()
    login_manager.authenticate(user=usr, pwd=pwd)
    login_manager.post_login()

    # Modify the response as needed
    user_doc = frappe.get_doc("User", usr)
    
    # # Generate API Key & Secret if not present
    # if not user_doc.api_key or not user_doc.api_secret:
    user_doc.api_key = frappe.generate_hash(length=15)
    raw = frappe.generate_hash(length=30)
    user_doc.api_secret = raw
    user_doc.save(ignore_permissions=True)

    return {
        "message": "Logged in",
        "email": usr,
        "first_name": user_doc.first_name,
        "last_name" : user_doc.last_name,
        "is_kyc":user_doc.is_kyc,
        "api_key": user_doc.api_key,
        "api_secret": raw
        # Add any custom data
        # "custom_flag": True,
        # "company": user_doc.default_company if user_doc.get("default_company") else None
    }

@frappe.whitelist(allow_guest=True)
def signup():
    try:
        # Get request data
        data = frappe.request.get_json()
        if not data:
            return {
                "message":"No request data found"
            }
        # Validate required fields
        required_fields = ['first_name', 'last_name', 'phone', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return error_response(f"Missing required field: {field}")
        
        # Extract parameters
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        email = data.get('email')
        phone = data.get('phone')
        password = data.get('password')
        
        # Validate email format
        if not validate_email_address(email):
            return error_response("Invalid email address format")
        
        # Check if email already exists
        if frappe.db.exists("User", {"email": email}):
            return error_response("Email already registered")
        
        if frappe.db.exists("User", {"mobile_no": phone}):
            return error_response("Mobile No. already registered") 

        # # Validate date of birth format
        # try:
        #     dob = getdate(date_of_birth)
        #     # Perform any age validation if required
        #     # For example, to ensure user is at least 18 years old:
        #     # today_date = getdate(today())
        #     # age = today_date.year - dob.year - ((today_date.month, today_date.day) < (dob.month, dob.day))
        #     # if age < 18:
        #     #    return error_response("You must be at least 18 years old to register")
        # except:
        #     return error_response("Invalid date format for date of birth. Use YYYY-MM-DD")
        
        # Validate password strength
        if len(password) < 8:
            return error_response("Password must be at least 8 characters long")
            
        # Create new user
        user = frappe.new_doc("User")
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.enabled = 1
        user.new_password = password
        user.mobile_no = phone
        user.user_type = "System User"
        user.insert(ignore_permissions=True)
        
        # Assign Role Profile
        user.role_profile_name = "API Partner"
        
        # Assign Module Profile
        # module_profile = frappe.get_doc("Module Profile", "API Partner")
        # for module in module_profile.modules:
        #     user.append("block_modules", {
        #         "module": module.module
        #     })
        
        # Save user with profiles
        user.save(ignore_permissions=True)
        
        # Add role directly to ensure it's applied
        if not frappe.db.exists("Has Role", {"parent": user.name, "role": "API Partner"}):
            role = user.append("roles", {})
            role.role = "API Partner"
            user.save(ignore_permissions=True)
        
        # Commit transaction
        frappe.db.commit()
        
        channel_partner = frappe.new_doc('Channel Partner')
        channel_partner.company_name = user.name
        channel_partner.status = "Active"

        channel_partner.append('team',
        {
            "person_name":user.name
        })

        channel_partner.save(ignore_permissions=True)

        frappe.db.commit()

        wallet = frappe.new_doc("Partner Wallet")
        wallet.channel_partner = channel_partner.name
        wallet.balance = 0
        wallet.status = "Active"

        wallet.save(ignore_permissions=True)
        frappe.db.commit()

        return success_response("User registered successfully as API Partner")
    
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), _("API Partner Signup Error"))
        return error_response(f"Registration failed: {str(e)}")

def success_response(message):
    """Return a success response in JSON format"""
    frappe.response["http_status_code"] = 200
    return {
        "status": "success",
        "message": message
    }

def error_response(message):
    """Return an error response in JSON format"""
    frappe.response["http_status_code"] = 400
    return {
        "status": "error",
        "message": message
    }

@frappe.whitelist()
def mark_kyc_done(user_email):
    try:
        user = frappe.get_doc("User", user_email)
        if user.is_kyc:
            return {
                "message":"Your KYC is already completed"
            }
        user.is_kyc = 1  # or True
        user.save(ignore_permissions=True)
        frappe.db.commit()  # optional, for immediate DB write

        products = frappe.get_all("Product")
        channel_partner = frappe.get_doc("Channel Partner",user_email)
        for product in products:
            channel_partner.append("product_pricing",{
                "product_name":product.name,
                "discount_type":"Fixed",
                "discount_amount":2,
                "plateform_fee_type":"Fixed",
                "plateform_fee":1
            })
        
        channel_partner.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            "first_name":user.first_name,
            "last_name":user.last_name,
            "is_kyc":user.is_kyc,
            "email":user.email,
            "full_name":user.full_name
        }
    except Exception as e:
        frappe.log_error("Error in updating KYC",f"{str(e)}")
        return {
            f"{str(e)}"
        }
    