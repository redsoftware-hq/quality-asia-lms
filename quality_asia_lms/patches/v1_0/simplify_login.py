"""QA-29: Simplify login page — disable email-link login.

The "Login with Email Link" button is controlled by a System Settings flag.
Disabling it here removes the button from the login page on migrate.

The "Login with Frappe Cloud" button is a runtime condition on Frappe Cloud
and cannot be suppressed via System Settings — it is hidden via CSS in
brand.css instead.
"""

import frappe


def execute():
	frappe.db.set_single_value("System Settings", "login_with_email_link", 0)
