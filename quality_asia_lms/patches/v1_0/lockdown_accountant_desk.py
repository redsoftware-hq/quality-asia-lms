"""QA-41: Lock down the Accountant (school@qualityasia.in) Desk surface.

Problems:
  - The account had LMS roles → the "Frappe Learning" / "Learning" app tiles
    appeared on the Desk (gated by ``lms.check_app_permission → has_lms_role``).
  - Public workspaces with no role restriction (e.g. the LMS "Learning"
    workspace) were visible to every Desk user.
  - The baseline "Desk User" perm let the account open /desk/user (PII).

Fixes:
  1. Strip every role except Accountant from school@qualityasia.in so the LMS
     app tiles disappear (no LMS role → ``has_lms_role`` returns False).
  2. Set ``default_app`` so the user lands on /desk (not /apps) and
     ``default_workspace`` = Finance (already set by seed_finance_workspace).
  3. A companion permission hook (accountant_lockdown.py) blocks the User list
     — registered in hooks.py, no Custom DocPerm changes here.

Does NOT affect outbound email — SMTP sending is governed by Email Account
settings, not User roles.

Idempotent — safe to re-run.
"""

import frappe

ACCOUNTANT_EMAIL = "school@qualityasia.in"
KEEP_ROLES = {"Accountant"}
# Frappe always grants these automatically; don't try to remove them.
AUTO_ROLES = {"All", "Guest", "Desk User"}


def execute():
	_strip_roles()
	_set_landing()
	frappe.db.commit()


def _strip_roles():
	"""Remove every non-Accountant role from the account."""
	if not frappe.db.exists("User", ACCOUNTANT_EMAIL):
		return

	user = frappe.get_doc("User", ACCOUNTANT_EMAIL)
	to_remove = []
	for role_row in user.roles:
		if role_row.role not in KEEP_ROLES and role_row.role not in AUTO_ROLES:
			to_remove.append(role_row.role)

	if not to_remove:
		return

	for role_name in to_remove:
		user.remove_roles(role_name)
	frappe.logger("qa_lms").info(
		f"Stripped roles from {ACCOUNTANT_EMAIL}: {', '.join(to_remove)}"
	)


def _set_landing():
	"""Force-land the account on /desk → Finance workspace."""
	if not frappe.db.exists("User", ACCOUNTANT_EMAIL):
		return
	# default_app blank → Frappe sends System Users to /desk (or /apps if
	# multiple apps visible, but with LMS roles stripped, only Desk remains).
	frappe.db.set_value(
		"User", ACCOUNTANT_EMAIL,
		{"default_workspace": "Finance", "default_app": ""},
		update_modified=False,
	)
