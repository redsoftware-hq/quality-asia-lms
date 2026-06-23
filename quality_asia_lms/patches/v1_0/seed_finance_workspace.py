"""QA-39: Pin the Accountant user's default workspace to Finance (one-time).

The Finance workspace is shipped as a module-level JSON file and synced on
every ``bench migrate``.  The ``User.validate`` hook in
``accountant_lockdown.py`` now auto-pins ``default_workspace = "Finance"``
for any user with the Accountant role.  This patch remains for the initial
school@qualityasia.in user on sites that already ran it.

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

	# Trigger the validate hook which pins workspace + default_app.
	user.save(ignore_permissions=True)
	frappe.db.commit()
