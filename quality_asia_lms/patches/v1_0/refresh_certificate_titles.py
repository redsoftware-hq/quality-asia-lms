"""QA-29 (B4): Refresh stale course_title on LMS Certificate records.

LMS Certificate.course_title is a fetch_from field that copies from
LMS Course.title at creation time. If a course title is later corrected
(e.g. from "ISO 26000" to "ISO 26000:2010"), existing certificates keep
the old value. This patch refreshes all certificates to match the current
course title.

Idempotent — safe to re-run. No-op when titles already match.
"""

import frappe


def execute():
	updated = 0
	certs = frappe.db.sql(
		"""
		SELECT c.name, c.course, c.course_title, lc.title AS current_title
		FROM `tabLMS Certificate` c
		JOIN `tabLMS Course` lc ON lc.name = c.course
		WHERE c.course_title != lc.title
		   OR c.course_title IS NULL
		""",
		as_dict=True,
	)
	for cert in certs:
		frappe.db.set_value(
			"LMS Certificate",
			cert.name,
			"course_title",
			cert.current_title,
			update_modified=False,
		)
		updated += 1

	if updated:
		frappe.db.commit()
		frappe.logger("qa_lms").info(f"Refreshed course_title on {updated} certificate(s)")
