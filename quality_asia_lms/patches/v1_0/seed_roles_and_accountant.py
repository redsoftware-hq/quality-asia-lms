"""QA-33 / QA-34: Create Accountant & Operations roles + school@qualityasia.in user.

Accountant: read-only on LMS Payment + QA Invoice (future), print+email.
Operations: read+write+create on Courses/Quizzes, read on Payments, no delete.

Both roles get no access to LMS Settings, User, or admin doctypes.

Idempotent — safe to re-run.
"""

import frappe
from frappe.utils import random_string


ACCOUNTANT_PERMS = [
	{"parent": "LMS Payment", "role": "Accountant", "permlevel": 0, "read": 1, "write": 0, "create": 0, "delete": 0, "print": 1, "email": 1, "export": 1},
	{"parent": "Address", "role": "Accountant", "permlevel": 0, "read": 1, "write": 0, "create": 0, "delete": 0, "print": 0, "email": 0, "export": 0},
]

OPERATIONS_PERMS = [
	{"parent": "LMS Course", "role": "Operations", "permlevel": 0, "read": 1, "write": 1, "create": 1, "delete": 0, "print": 0, "email": 0, "export": 1},
	{"parent": "LMS Quiz", "role": "Operations", "permlevel": 0, "read": 1, "write": 1, "create": 1, "delete": 0, "print": 0, "email": 0, "export": 1},
	{"parent": "LMS Question", "role": "Operations", "permlevel": 0, "read": 1, "write": 1, "create": 1, "delete": 0, "print": 0, "email": 0, "export": 1},
	{"parent": "LMS Payment", "role": "Operations", "permlevel": 0, "read": 1, "write": 0, "create": 0, "delete": 0, "print": 1, "email": 0, "export": 1},
	{"parent": "LMS Certificate", "role": "Operations", "permlevel": 0, "read": 1, "write": 0, "create": 0, "delete": 0, "print": 1, "email": 0, "export": 1},
	{"parent": "LMS Enrollment", "role": "Operations", "permlevel": 0, "read": 1, "write": 0, "create": 0, "delete": 0, "print": 0, "email": 0, "export": 1},
]


def execute():
	_ensure_role("Accountant")
	_ensure_role("Operations")

	for perm in ACCOUNTANT_PERMS + OPERATIONS_PERMS:
		_upsert_custom_docperm(perm)

	_seed_accountant_user()
	frappe.db.commit()


def _ensure_role(role_name):
	if not frappe.db.exists("Role", role_name):
		frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1}).insert(ignore_permissions=True)


def _upsert_custom_docperm(perm):
	"""Insert or update a Custom DocPerm row.

	Calls ``setup_custom_perms`` first so that the doctype's standard DocPerm
	rows are cloned into Custom DocPerm before we add ours.  Without this step,
	Frappe discards ALL standard permissions for the doctype as soon as a single
	Custom DocPerm row exists — silently stripping roles like LMS Student.
	"""
	from frappe.permissions import setup_custom_perms

	setup_custom_perms(perm["parent"])  # no-op when Custom DocPerm already exists

	existing = frappe.db.exists(
		"Custom DocPerm",
		{"parent": perm["parent"], "role": perm["role"], "permlevel": perm["permlevel"]},
	)
	if existing:
		frappe.db.set_value("Custom DocPerm", existing, perm, update_modified=False)
	else:
		doc = frappe.new_doc("Custom DocPerm")
		doc.update(perm)
		doc.insert(ignore_permissions=True)


def _seed_accountant_user():
	email = "school@qualityasia.in"
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.add_roles("Accountant")
		return

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Quality Asia",
			"last_name": "School",
			"enabled": 1,
			"new_password": random_string(16),
			"send_welcome_email": 0,
			"user_type": "System User",
		}
	)
	user.flags.ignore_permissions = True
	user.flags.ignore_password_policy = True
	user.insert()
	user.add_roles("Accountant")
	frappe.logger("qa_lms").info(f"Created accountant user {email}")
