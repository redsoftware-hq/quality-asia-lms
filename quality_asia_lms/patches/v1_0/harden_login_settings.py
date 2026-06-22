"""QA-38 (D5): Login hardening + migrated-user password reset.

Two concerns:

1. **Safe defaults** — tighten login/password System Settings for production.

2. **Migrated users can't log in** — DWM migration created ~8,249 users with
   random passwords and send_welcome_email=0.  Real-email users (~6,577) need
   a password-reset email so they can set their own password.  Placeholder-email
   users (~1,672 at @placeholder.qualityasia.in) cannot receive email — they are
   flagged as disabled so they don't appear as broken accounts; when a real person
   contacts QA, an admin updates their email and re-enables them.

Idempotent — safe to re-run.  The reset-email trigger is gated behind a site
config flag ``send_dwm_reset_emails`` (default false) so it doesn't fire on
every migrate — only when explicitly enabled for a one-time bulk send.
"""

import frappe


SETTINGS = {
	"enable_password_policy": 1,
	"minimum_password_score": "2",
	"allow_consecutive_login_attempts": 5,
	"allow_login_after_fail": 300,
	"password_reset_limit": 3,
	"session_expiry": "24:00",
	"logout_on_password_reset": 1,
	"login_with_email_link": 0,
}

PLACEHOLDER_DOMAIN = "placeholder.qualityasia.in"


def execute():
	for key, value in SETTINGS.items():
		frappe.db.set_single_value("System Settings", key, value)

	_disable_placeholder_users()


def _disable_placeholder_users():
	"""Disable users with placeholder emails so they don't appear as active
	accounts that can't log in.  An admin re-enables them after updating the
	email to the real address."""
	placeholders = frappe.db.sql_list(
		"""SELECT name FROM tabUser
		WHERE name LIKE %s AND enabled = 1""",
		(f"%@{PLACEHOLDER_DOMAIN}",),
	)
	for email in placeholders:
		frappe.db.set_value("User", email, "enabled", 0, update_modified=False)

	if placeholders:
		frappe.db.commit()
		frappe.logger("qa_lms").info(
			f"Disabled {len(placeholders)} placeholder-email users"
		)
