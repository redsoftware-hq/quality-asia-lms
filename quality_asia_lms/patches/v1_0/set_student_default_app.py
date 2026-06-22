"""QA-39: Set default_app='lms' for all Website Users (students).

After login, Frappe routes Website Users to get_default_path() which honours
User.default_app.  Setting it to 'lms' ensures students always land on the
LMS frontend instead of the /apps chooser or an unexpected page.

System Users (admins, operations, etc.) are excluded automatically by the
user_type filter and continue to land on Desk.

Idempotent — re-runs skip users who already have default_app set.
"""

import frappe


def execute():
	students = frappe.db.sql_list(
		"""SELECT name FROM tabUser
		WHERE user_type = 'Website User'
		  AND (default_app IS NULL OR default_app = '')"""
	)
	for email in students:
		frappe.db.set_value("User", email, "default_app", "lms", update_modified=False)

	if students:
		frappe.db.commit()
		frappe.logger("qa_lms").info(
			f"Set default_app='lms' for {len(students)} Website Users"
		)
