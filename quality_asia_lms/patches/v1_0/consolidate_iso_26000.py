"""Consolidate the duplicate ISO 26000 course.

The old 'iso-26000' course was created manually before QA-24 seeding. The DWM
migration attached 212 enrollments and certificates to it. QA-24 then seeded
the canonical slug 'free-certified-internal-auditor-training-on-iso-26000-
social-responsibility', creating a duplicate.

This patch:
  1. Reassigns enrollments from old → canonical slug
  2. Reassigns certificates from old → canonical slug
  3. Deletes the old course's lessons and chapters
  4. Deletes the old 'iso-26000' course

Idempotent: skips silently if 'iso-26000' does not exist.
"""

import frappe

OLD = "iso-26000"
NEW = "free-certified-internal-auditor-training-on-iso-26000-social-responsibility"


def execute():
	if not frappe.db.exists("LMS Course", OLD):
		return

	if not frappe.db.exists("LMS Course", NEW):
		frappe.log_error(
			title="consolidate_iso_26000: canonical course missing",
			message=f"Cannot consolidate — target course '{NEW}' does not exist.",
		)
		return

	# 1. Reassign enrollments
	moved_enroll = frappe.db.sql(
		"UPDATE `tabLMS Enrollment` SET course = %s WHERE course = %s",
		(NEW, OLD),
	)
	enroll_count = frappe.db.sql(
		"SELECT ROW_COUNT()",
	)[0][0]

	# 2. Reassign certificates
	frappe.db.sql(
		"UPDATE `tabLMS Certificate` SET course = %s WHERE course = %s",
		(NEW, OLD),
	)
	cert_count = frappe.db.sql(
		"SELECT ROW_COUNT()",
	)[0][0]

	# 3. Delete old course's lessons and chapters (order: lessons first)
	for lesson in frappe.get_all("Course Lesson", filters={"course": OLD}, pluck="name"):
		frappe.delete_doc("Course Lesson", lesson, force=True, ignore_permissions=True)

	for chapter in frappe.get_all("Course Chapter", filters={"course": OLD}, pluck="name"):
		frappe.delete_doc("Course Chapter", chapter, force=True, ignore_permissions=True)

	# 4. Delete the old course
	frappe.delete_doc("LMS Course", OLD, force=True, ignore_permissions=True)

	print(
		f"[consolidate_iso_26000] Moved {enroll_count} enrollment(s) and "
		f"{cert_count} certificate(s) from '{OLD}' → '{NEW}'. Old course deleted."
	)
