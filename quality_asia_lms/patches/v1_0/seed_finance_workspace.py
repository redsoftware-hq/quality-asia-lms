"""QA-39: Create a minimal Finance workspace for the Accountant role.

The Accountant user (school@qualityasia.in) should land on a clean page showing
only a shortcut to the LMS Payment list — no distracting sidebar items or
default workspaces. This patch:
1. Creates a "Finance" Workspace with a single LMS Payment shortcut.
2. Restricts visibility to the Accountant role.
3. Pins the Accountant user's default_workspace so they land here on login.

Idempotent — safe to re-run.
"""

import frappe


WORKSPACE_NAME = "Finance"
ACCOUNTANT_EMAIL = "school@qualityasia.in"


def execute():
	_create_workspace()
	_pin_user_workspace()
	frappe.db.commit()


def _create_workspace():
	if frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	ws = frappe.new_doc("Workspace")
	ws.name = WORKSPACE_NAME
	ws.label = WORKSPACE_NAME
	ws.title = WORKSPACE_NAME
	ws.is_hidden = 0
	ws.public = 1
	ws.content = "[]"

	ws.append("roles", {"role": "Accountant"})

	ws.append(
		"shortcuts",
		{
			"label": "Payments",
			"type": "DocType",
			"link_to": "LMS Payment",
			"color": "Red",
			"format": "{} payments",
			"stats_filter": '{"payment_received": 1}',
		},
	)

	ws.flags.ignore_permissions = True
	ws.flags.ignore_links = True
	ws.insert()
	frappe.logger("qa_lms").info(f"Created workspace '{WORKSPACE_NAME}'")


def _pin_user_workspace():
	if not frappe.db.exists("User", ACCOUNTANT_EMAIL):
		return
	frappe.db.set_value("User", ACCOUNTANT_EMAIL, "default_workspace", WORKSPACE_NAME)
