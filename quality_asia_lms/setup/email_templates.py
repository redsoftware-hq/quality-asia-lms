"""Wire the QA Certification Email template into LMS Settings (after_migrate).

Idempotent: only sets the template when the LMS Setting is empty, so a manual
choice in the Desk UI is never overwritten.
"""

import frappe

TEMPLATE_NAME = "QA Certification Email"


def ensure_certification_template():
	"""Point LMS Settings → certification_template at our shipped template."""
	if not frappe.db.exists("Email Template", TEMPLATE_NAME):
		return

	current = frappe.db.get_single_value("LMS Settings", "certification_template")
	if current:
		return  # don't clobber a manual choice

	frappe.db.set_single_value("LMS Settings", "certification_template", TEMPLATE_NAME)
	frappe.db.commit()
