app_name = "quality_asia_lms"
app_title = "Quality Asia LMS"
app_publisher = "Red Software"
app_description = "Custom Frappe app for Quality Asia LMS"
app_email = "kirtan.tank@redsoftware.in"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "quality_asia_lms",
# 		"logo": "/assets/quality_asia_lms/logo.png",
# 		"title": "Quality Asia LMS",
# 		"route": "/quality_asia_lms",
# 		"has_permission": "quality_asia_lms.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/quality_asia_lms/css/quality_asia_lms.css"
# app_include_js = "/assets/quality_asia_lms/js/quality_asia_lms.js"

# include css in header of web template (login page, portal pages, etc.)
# Brand skin + login-page cleanup (hide Frappe Cloud / Email Link buttons).
web_include_css = "/assets/quality_asia_lms/css/brand.css"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "quality_asia_lms/public/scss/website"

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
# app_include_icons = "quality_asia_lms/public/icons.svg"

# Home Pages
# ----------

# Send guests to the LMS frontend instead of /login.
home_page = "lms"

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
# Exposes format_training_dates() to the QA Certificate print format.
jinja = {
	"methods": [
		"quality_asia_lms.overrides.certificate.format_training_dates",
		"quality_asia_lms.overrides.certificate.qa_cert_image",
		"quality_asia_lms.overrides.invoice.get_invoice_context",
	],
}

# Custom self-signup form (Name, Email, mandatory Mobile, optional Address) on
# Frappe's /login#signup page. Wins over the stock/LMS form because this app
# loads last (login.py uses signup_form_template[-1]).
signup_form_template = "quality_asia_lms.overrides.signup.get_signup_template"

# Installation
# ------------

# before_install = "quality_asia_lms.install.before_install"
after_install = "quality_asia_lms.brand.inject_brand_css"

# Re-inject the brand skin <link> into the (build-generated) LMS SPA shell.
# bench update runs build -> migrate, so after_migrate self-heals the link.
# Also re-point existing certificates onto the QA print format (runs after the
# fixtures that create that print format are synced).
after_migrate = [
	"quality_asia_lms.brand.inject_brand_css",
	"quality_asia_lms.overrides.certificate.enforce_qa_certificate_template",
	"quality_asia_lms.overrides.dwm_migration.migrate_if_dump_present",
]

# Uninstallation
# ------------

# before_uninstall = "quality_asia_lms.uninstall.before_uninstall"
# after_uninstall = "quality_asia_lms.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "quality_asia_lms.utils.before_app_install"
# after_app_install = "quality_asia_lms.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "quality_asia_lms.utils.before_app_uninstall"
# after_app_uninstall = "quality_asia_lms.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "quality_asia_lms.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# Block Accountant-only users from listing or reading User records (and any
# other sensitive doctype reachable via the baseline "Desk User" perm).
# Uses a permission hook — NOT Custom DocPerm — so it can't re-trigger the
# perm-wipe that broke enrollment (see QA-38).
permission_query_conditions = {
	"User": "quality_asia_lms.overrides.accountant_lockdown.user_query_conditions",
}

has_permission = {
	"User": "quality_asia_lms.overrides.accountant_lockdown.user_has_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

override_doctype_class = {
	"Razorpay Settings": "quality_asia_lms.overrides.razorpay_settings.RazorpaySettings",
	# Attach the certificate PDF to the certification email (in-memory, no File stored).
	"LMS Certificate": "quality_asia_lms.overrides.certificate.QALMSCertificate",
}

# Document Events
# ---------------
# Hook on document methods and events

# Force every generated certificate onto the QA print format and auto-fill the
# two training dates from the issue date.
doc_events = {
	"LMS Certificate": {
		"before_insert": "quality_asia_lms.overrides.certificate.prepare_certificate",
	},
	"LMS Course": {
		"before_insert": "quality_asia_lms.overrides.mentor.auto_assign_mentor",
		"before_save": "quality_asia_lms.overrides.course.sync_paid_category",
	},
	"LMS Payment": {
		"on_update": "quality_asia_lms.overrides.invoice.on_payment_update",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"quality_asia_lms.tasks.all"
# 	],
# 	"daily": [
# 		"quality_asia_lms.tasks.daily"
# 	],
# 	"hourly": [
# 		"quality_asia_lms.tasks.hourly"
# 	],
# 	"weekly": [
# 		"quality_asia_lms.tasks.weekly"
# 	],
# 	"monthly": [
# 		"quality_asia_lms.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "quality_asia_lms.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "quality_asia_lms.event.get_events"
# }
override_whitelisted_methods = {
	# Force India server-side so the browser-supplied country cannot skip 18% GST.
	"lms.lms.payments.get_payment_link": "quality_asia_lms.overrides.payments.get_payment_link",
	"lms.lms.utils.get_order_summary": "quality_asia_lms.overrides.payments.get_order_summary",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "quality_asia_lms.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["quality_asia_lms.utils.before_request"]
# Inject the brand skin <link> into the LMS SPA shell at SERVE time. This is the
# deploy-safe path: Frappe Cloud ships apps read-only, so editing _lms.html on
# disk (after_migrate, below) can't stick there — rewriting the response can.
after_request = ["quality_asia_lms.brand.inject_brand_css_into_response"]

# Job Events
# ----------
# before_job = ["quality_asia_lms.utils.before_job"]
# after_job = ["quality_asia_lms.utils.after_job"]

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
# 	"quality_asia_lms.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# Fixtures
# --------
# Shipped-as-code customizations re-applied on every `bench migrate`:
#   - the two training-date Custom Fields on LMS Certificate
#   - the Property Setter that makes "QA Certificate" the default print format
#   - the "QA Certificate" print format itself
# Order matters: the print format is imported before the Property Setter that names it.
fixtures = [
	{
		"dt": "Custom Field",
		"filters": [["name", "in", [
			"LMS Certificate-training_start_date",
			"LMS Certificate-training_end_date",
			"LMS Certificate-training_dates",
			"LMS Certificate-candidate_name_as_printed",
			"LMS Payment-invoice_number",
			"LMS Payment-invoice_emailed",
			"User-company_name",
			"User-address",
			"User-resume",
		]]],
	},
	{
		"dt": "Print Format",
		"filters": [["name", "in", ["QA Certificate", "QA Invoice"]]],
	},
	{
		"dt": "Property Setter",
		"filters": [["name", "in", [
			"LMS Certificate-main-default_print_format",
			"LMS Payment-main-default_print_format",
		]]],
	},
]

