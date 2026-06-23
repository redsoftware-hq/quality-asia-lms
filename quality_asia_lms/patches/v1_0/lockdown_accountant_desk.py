"""QA-41: Lock down the Accountant Desk surface (one-time migration).

Superseded by the ``User.validate`` hook in ``accountant_lockdown.py`` which
now enforces the same lockdown for ANY user assigned the Accountant role —
no hardcoded emails.  This patch remains for sites that already ran it; the
hook handles all future cases.

Idempotent — safe to re-run.
"""

import frappe

ACCOUNTANT_EMAIL = "school@qualityasia.in"


def execute():
	if not frappe.db.exists("User", ACCOUNTANT_EMAIL):
		return

	user = frappe.get_doc("User", ACCOUNTANT_EMAIL)
	if "Accountant" not in {r.role for r in user.roles}:
		return

	# Trigger the validate hook which does the actual lockdown.
	user.save(ignore_permissions=True)
	frappe.db.commit()
