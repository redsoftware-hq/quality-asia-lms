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

import time

import frappe

OLD = "iso-26000"
NEW = "free-certified-internal-auditor-training-on-iso-26000-social-responsibility"

MAX_RETRIES = 3


def _sql_with_retry(query, values):
	for attempt in range(MAX_RETRIES):
		try:
			frappe.db.sql(query, values)
			return frappe.db.sql("SELECT ROW_COUNT()")[0][0]
		except frappe.QueryDeadlockError:
			if attempt == MAX_RETRIES - 1:
				raise
			frappe.db.rollback()
			time.sleep(1 * (attempt + 1))


def _with_retry(fn):
	"""Run *fn* with deadlock retry (for ORM delete_doc calls)."""
	for attempt in range(MAX_RETRIES):
		try:
			return fn()
		except frappe.QueryDeadlockError:
			if attempt == MAX_RETRIES - 1:
				raise
			frappe.db.rollback()
			time.sleep(1 * (attempt + 1))


def execute():
	if not frappe.db.exists("LMS Course", OLD):
		return

	if not frappe.db.exists("LMS Course", NEW):
		frappe.throw(
			f"Cannot consolidate — target course '{NEW}' does not exist. "
			"The old duplicate will remain until this is resolved.",
			title="consolidate_iso_26000: canonical course missing",
		)

	# 1. Reassign enrollments
	enroll_count = _sql_with_retry(
		"UPDATE `tabLMS Enrollment` SET course = %s WHERE course = %s",
		(NEW, OLD),
	)

	# 2. Reassign certificates
	cert_count = _sql_with_retry(
		"UPDATE `tabLMS Certificate` SET course = %s WHERE course = %s",
		(NEW, OLD),
	)

	# 3. Delete old course's lessons and chapters (order: lessons first)
	for lesson in frappe.get_all("Course Lesson", filters={"course": OLD}, pluck="name"):
		_with_retry(lambda n=lesson: frappe.delete_doc("Course Lesson", n, force=True, ignore_permissions=True))

	for chapter in frappe.get_all("Course Chapter", filters={"course": OLD}, pluck="name"):
		_with_retry(lambda n=chapter: frappe.delete_doc("Course Chapter", n, force=True, ignore_permissions=True))

	# 4. Delete the old course
	_with_retry(lambda: frappe.delete_doc("LMS Course", OLD, force=True, ignore_permissions=True))

	print(
		f"[consolidate_iso_26000] Moved {enroll_count} enrollment(s) and "
		f"{cert_count} certificate(s) from '{OLD}' → '{NEW}'. Old course deleted."
	)
