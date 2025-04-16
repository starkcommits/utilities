import frappe

def update_wallet(doc, method):
    """Update wallet balance safely for reversals or top-ups using DB row locking"""

    try:
        # Fetch & Lock Wallet Row
        wallet_data = frappe.db.sql("""
            SELECT name, balance FROM `tabPartner Wallet`
            WHERE channel_partner = %s AND status = "Active" 
            FOR UPDATE
        """, (doc.channel_partner,), as_dict=True)

        if not wallet_data:
            frappe.throw("No Active wallet found for this channel partner.")

        wallet_name = wallet_data[0]["name"]
        wallet_balance = wallet_data[0]["balance"]
        new_balance = wallet_balance  # Default: No change

        # **Only handle reversals or top-ups**
        if doc.status == "Reversed" or (doc.status == "Completed" and doc.product_name == "Wallet Top Up"):
            new_balance = wallet_balance + doc.transaction_amount

            # Update Wallet Balance
            frappe.db.sql("""
                UPDATE `tabPartner Wallet`
                SET balance = %s
                WHERE name = %s
            """, (new_balance, wallet_name))

            # Update Payment Transaction Logs
            frappe.db.sql("""
                UPDATE `tabPayment Transaction Logs`
                SET closing_balance = %s
                WHERE name = %s
            """, (new_balance, doc.name))

        frappe.db.commit()  # ✅ Commit at the end

    except Exception as e:
        frappe.db.rollback()  # ✅ Rollback in case of failure
        frappe.log_error(f"Wallet Update Error: {str(e)}", "Wallet Update Failure")
        raise

@frappe.whitelist(allow_guest=True)
def get_balance(user_email):
    try:
        wallet = frappe.get_doc("Partner Wallet",user_email)
        if not wallet:
            return {
                "message": "No wallet found"
            }
        return {
            "balance":wallet.balance,
            "pin":wallet.pin,
            "status":wallet.status
        }
    except Exception as e:
        frappe.log_error("Error in balance fetching",f"{str(e)}")

        return {
            "error":f"{str(e)}"
        }


@frappe.whitelist(allow_guest=True)
def update_pin(user_email, pin):
    
    try:
        # Fetch & Lock Wallet Row
        wallet_data = frappe.db.sql("""
            SELECT name, balance FROM `tabPartner Wallet`
            WHERE channel_partner = %s FOR UPDATE
        """, (user_email,), as_dict=True)

        if not wallet_data:
            frappe.db.commit()
            frappe.throw("No wallet found for this channel partner.")
            return {
                "message":"No active wallet found"
            }

        # Update Wallet Pin
        frappe.db.sql("""
            UPDATE `tabPartner Wallet`
            SET pin = %s
            WHERE name = %s
        """, (pin, wallet_data[0]["name"]))


        frappe.db.commit()

        return {
            "message":"Pin updated successfully"
        }

    except Exception as e:
        frappe.log_error("Error in balance fetching",f"{str(e)}")

        return {
            "error":f"{str(e)}"
        }

# @frappe.whitelist()
# def topup(user_email,balance):
#     try:
#         # Fetch & Lock Wallet Row
#         wallet_data = frappe.db.sql("""
#             SELECT name, balance FROM `tabPartner Wallet`
#             WHERE channel_partner = %s FOR UPDATE
#         """, (user_email,), as_dict=True)

#         if not wallet_data:
#             frappe.db.commit()
#             frappe.throw("No wallet found for this channel partner.")
#             return {
#                 "message":"No active wallet found"
#             }

#         wallet_name = wallet_data[0]["name"]
#         wallet_balance = wallet_data[0]["balance"]
#         new_balance = wallet_balance + balance
#         # Update Wallet Balance
#         frappe.db.sql("""
#             UPDATE `tabPartner Wallet`
#             SET balance = %s
#             WHERE name = %s
#         """, (new_balance,wallet_name))


#         frappe.db.commit()

#         return {
#             "message":"wallet recharged successfully",
#             "balance":new_balance
#         }

#     except Exception as e:
#         frappe.log_error("Error in balance fetching",f"{str(e)}")

#         return {
#             "error":f"{str(e)}"
#         }


@frappe.whitelist()
def withdraw(user_email,balance):
    try:
        # Fetch & Lock Wallet Row
        wallet_data = frappe.db.sql("""
            SELECT name, balance FROM `tabPartner Wallet`
            WHERE channel_partner = %s FOR UPDATE
        """, (user_email,), as_dict=True)

        if not wallet_data:
            frappe.throw("No wallet found for this channel partner.")
            return {
                "message":"No active wallet found"
            }

        wallet_name = wallet_data[0]["name"]
        wallet_balance = wallet_data[0]["balance"]

        if(wallet_balance<balance):
            frappe.db.commit()
            return {
                "message":"Hey, you are going out of your wallet balance"
            }
        
        new_balance = wallet_balance - balance
        # Update Wallet Balance
        frappe.db.sql("""
            UPDATE `tabPartner Wallet`
            SET balance = %s
            WHERE name = %s
        """, (new_balance,wallet_name))


        frappe.db.commit()

        return {
            "message":"Money withdraw successfully",
            "balance":new_balance
        }
    except Exception as e:
        frappe.log_error("Error in balance fetching",f"{str(e)}")

        return {
            "error":f"{str(e)}"
        }





@frappe.whitelist()
def topup(user_email, balance, pin):
    try:
        wallet = frappe.get_doc("Partner Wallet",user_email)

        if wallet.status !="Active":
            return {
                "message":"Your wallet is not active. Please contact admininstrator"
            }

        if wallet.pin != pin:
            return {
                "Your pin is incorrect. Enter your correct pin."
            }
        # Create an order
        order = frappe.get_doc({
            "doctype": "Orders",
            "order_amount": balance,
            "product_name": "Wallet Top Up",
            "channel": "Android",
            "channel_partner": user_email,
            "order_status": "Created"
        })
        order.insert(ignore_permissions=True)
        frappe.db.commit()
        
        
        order.order_status="Completed"
        order.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            "status": "success",
            "message":"Wallet recharged successfully" ,
            "order_id":order.name
        }

    except Exception as e:
        frappe.log_error("Error in wallet topup processing",f"{str(e)}")
        return {"Error":f"{str(e)}"}
