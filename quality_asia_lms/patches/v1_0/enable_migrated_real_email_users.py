"""QA-40: Re-enable disabled migrated users who have a real email.

DWM-migrated users with genuine email addresses were accidentally disabled on
the live site.  They should be able to self-serve a password reset via the
login page's "Forgot Password" flow — which requires the account to be enabled
(Frappe silently skips disabled users in ``reset_password``).

Placeholder accounts (@placeholder.qualityasia.in) stay disabled until an
admin reconciles their email via ``migrated_users.update_placeholder_email``.

Idempotent — safe to re-run on every migrate.
"""

from quality_asia_lms.overrides.migrated_users import enable_real_email_users


def execute():
	enable_real_email_users()
