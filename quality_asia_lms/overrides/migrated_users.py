"""Utilities for managing DWM-migrated users who can't log in.

Migrated users were created with random passwords and no welcome email.
This module provides admin tools to help them set their first password.

Usage (inside ``make shell`` → ``cd /workspace/dev-bench``):

  # Dry run — count how many users would receive reset emails
  bench --site development.qa-lms execute \
    quality_asia_lms.overrides.migrated_users.send_reset_emails \
    --kwargs "{'dry_run': True}"

  # Actually send (disable_emails must be 0 in site config)
  bench --site development.qa-lms execute \
    quality_asia_lms.overrides.migrated_users.send_reset_emails

  # Update a placeholder user's email (admin reconciliation)
  bench --site development.qa-lms execute \
    quality_asia_lms.overrides.migrated_users.update_placeholder_email \
    --kwargs "{'old_email': 'nomail-abc@placeholder.qualityasia.in', 'new_email': 'real@example.com'}"
"""

import frappe
from frappe.utils import get_url

PLACEHOLDER_DOMAIN = "placeholder.qualityasia.in"


def send_reset_emails(dry_run=False):
	"""Send password-reset emails to all enabled migrated users with real emails.

	Only targets Website Users who have never logged in (last_login is NULL or
	empty) and don't have a placeholder email.  Idempotent — Frappe's
	reset_password is safe to call multiple times."""
	users = frappe.db.sql(
		"""SELECT name, first_name FROM tabUser
		WHERE user_type = 'Website User'
		  AND enabled = 1
		  AND name NOT LIKE %s
		  AND (last_login IS NULL OR last_login = '')""",
		(f"%@{PLACEHOLDER_DOMAIN}",),
		as_dict=True,
	)

	if dry_run:
		print(f"Would send reset emails to {len(users)} users")
		for u in users[:10]:
			print(f"  {u.name} ({u.first_name})")
		if len(users) > 10:
			print(f"  ... and {len(users) - 10} more")
		return

	sent = 0
	failed = 0
	for user in users:
		try:
			frappe.get_doc("User", user.name).reset_password()
			sent += 1
		except Exception:
			frappe.log_error(title=f"Reset email failed for {user.name}")
			failed += 1

	frappe.db.commit()
	msg = f"Password reset emails: sent={sent} failed={failed} total={len(users)}"
	print(msg)
	frappe.logger("qa_lms").info(msg)


def update_placeholder_email(old_email, new_email):
	"""Admin tool: replace a placeholder email with the user's real email,
	re-enable the account, and trigger a password-reset email."""
	if not frappe.db.exists("User", old_email):
		frappe.throw(f"User {old_email} not found")

	new_email = (new_email or "").strip().lower()
	if not new_email or "@" not in new_email:
		frappe.throw("Invalid new email")

	if frappe.db.exists("User", new_email):
		frappe.throw(f"User {new_email} already exists — manual merge needed")

	frappe.rename_doc("User", old_email, new_email, merge=False)
	frappe.db.set_value("User", new_email, {"enabled": 1, "email": new_email})
	frappe.db.commit()

	frappe.get_doc("User", new_email).reset_password()
	print(f"Updated {old_email} → {new_email}, enabled, reset email sent")


def enable_real_email_users(dry_run=False):
	"""Re-enable disabled Website Users whose email is real (non-placeholder).

	DWM-migrated users with genuine email addresses should be able to self-serve
	a password reset.  Placeholder accounts (@placeholder.qualityasia.in) stay
	disabled until an admin reconciles their email.

	Idempotent — safe to re-run."""
	users = frappe.db.sql(
		"""SELECT name, first_name FROM tabUser
		WHERE user_type = 'Website User'
		  AND enabled = 0
		  AND name NOT LIKE %s""",
		(f"%@{PLACEHOLDER_DOMAIN}",),
		as_dict=True,
	)

	if dry_run:
		print(f"Would re-enable {len(users)} disabled real-email users")
		for u in users[:10]:
			print(f"  {u.name} ({u.first_name})")
		if len(users) > 10:
			print(f"  ... and {len(users) - 10} more")
		return

	enabled = 0
	for user in users:
		frappe.db.set_value("User", user.name, "enabled", 1, update_modified=False)
		enabled += 1

	if enabled:
		frappe.db.commit()
	msg = f"Re-enabled {enabled} disabled real-email users (total candidates: {len(users)})"
	print(msg)
	frappe.logger("qa_lms").info(msg)
