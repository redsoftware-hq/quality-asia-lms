"""QA-49: Backfill ``is_migrated`` on existing DWM-migrated certificates and users.

Migrated certificates are identified by having a non-empty
``candidate_name_as_printed`` custom field — set exclusively by the DWM
migration (``dwm_migration.py``).  Migrated users are those who own at
least one migrated certificate, plus all placeholder-email accounts.

Idempotent — safe to re-run on every migrate.
"""

import frappe

from quality_asia_lms.overrides.migrated_users import PLACEHOLDER_DOMAIN


def execute():
	# 1. Flag migrated certificates (candidate_name_as_printed is only set by the migration)
	certs_flagged = frappe.db.sql("""
		UPDATE `tabLMS Certificate`
		SET is_migrated = 1
		WHERE IFNULL(candidate_name_as_printed, '') != ''
		  AND IFNULL(is_migrated, 0) = 0
	""")

	# 2. Flag users who own a migrated certificate
	frappe.db.sql("""
		UPDATE tabUser u
		INNER JOIN `tabLMS Certificate` c ON c.member = u.name AND c.is_migrated = 1
		SET u.is_migrated = 1
		WHERE IFNULL(u.is_migrated, 0) = 0
	""")

	# 3. Flag all placeholder-email users (even those without certificates)
	frappe.db.sql(
		"""
		UPDATE tabUser
		SET is_migrated = 1
		WHERE name LIKE %s
		  AND IFNULL(is_migrated, 0) = 0
		""",
		(f"%@{PLACEHOLDER_DOMAIN}",),
	)

	frappe.db.commit()

	migrated_certs = frappe.db.count("LMS Certificate", {"is_migrated": 1})
	migrated_users = frappe.db.count("User", {"is_migrated": 1})
	print(f"is_migrated backfill: {migrated_certs} certificates, {migrated_users} users")
