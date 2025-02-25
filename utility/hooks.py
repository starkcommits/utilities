app_name = "utility"
app_title = "Utility"
app_publisher = "xFer India100x pvt. ltd."
app_description = "Utility"
app_email = "xfer@india100x.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "utility",
# 		"logo": "/assets/utility/logo.png",
# 		"title": "Utility",
# 		"route": "/utility",
# 		"has_permission": "utility.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/utility/css/utility.css"
# app_include_js = "/assets/utility/js/utility.js"

# include js, css files in header of web template
# web_include_css = "/assets/utility/css/utility.css"
# web_include_js = "/assets/utility/js/utility.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "utility/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "utility/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "utility.utils.jinja_methods",
# 	"filters": "utility.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "utility.install.before_install"
# after_install = "utility.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "utility.uninstall.before_uninstall"
# after_uninstall = "utility.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "utility.utils.before_app_install"
# after_app_install = "utility.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "utility.utils.before_app_uninstall"
# after_app_uninstall = "utility.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "utility.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Payment Transaction Logs": {
		# "after_insert": "utility.wallet.update_wallet",
		"on_update": "utility.wallet_utils.update_wallet"
	},
	"Orders":{
		"on_update": "utility.transaction.make_transaction"
	}
}

api = {
	"methods": [
		"utility.get_provider.get_provider_detail",
		"utility.fetch_plan.get_plans",
		"utility.api.make_an_order",
		"utility.create_order.make_an_order",
		"utility.api.topup",
		"utility.api.bulk_recharge",
		"utility.api.delete_record"
	]
}
# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"utility.tasks.all"
# 	],
# 	"daily": [
# 		"utility.tasks.daily"
# 	],
# 	"hourly": [
# 		"utility.tasks.hourly"
# 	],
# 	"weekly": [
# 		"utility.tasks.weekly"
# 	],
# 	"monthly": [
# 		"utility.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "utility.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "utility.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "utility.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["utility.utils.before_request"]
# after_request = ["utility.utils.after_request"]

# Job Events
# ----------
# before_job = ["utility.utils.before_job"]
# after_job = ["utility.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"utility.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

