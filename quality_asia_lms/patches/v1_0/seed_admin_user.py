"""QA-29: Seed samarth@qualityasia.in as System Administrator.

Creates the user if it doesn't exist and assigns System Manager + Administrator
roles (equivalent to System Administrator access). Idempotent.
"""

import frappe
from frappe.utils import random_string


def execute():
	email = "samarth@qualityasia.in"
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.add_roles("System Manager", "Administrator")
		return

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Samarth",
			"last_name": "Suri",
			"enabled": 1,
			"new_password": random_string(16),
			"send_welcome_email": 0,
			"user_type": "System User",
		}
	)
	user.flags.ignore_permissions = True
	user.flags.ignore_password_policy = True
	user.insert()
	user.add_roles("System Manager", "Administrator")
	frappe.logger("qa_lms").info(f"Created admin user {email}")
