"""QA-32: Add Samarth Suri as instructor on all existing courses.

Appends to the ``instructors`` child table on each ``LMS Course`` where
samarth@qualityasia.in is not already listed.  Future courses are handled
by a ``before_insert`` hook (see hooks.py / overrides/mentor.py).

Idempotent — safe to re-run.
"""

import frappe

MENTOR_EMAIL = "samarth@qualityasia.in"


def execute():
	if not frappe.db.exists("User", MENTOR_EMAIL):
		return

	courses = frappe.get_all("LMS Course", pluck="name")
	for course_name in courses:
		already = frappe.db.exists(
			"Course Instructor",
			{"parent": course_name, "instructor": MENTOR_EMAIL},
		)
		if already:
			continue

		doc = frappe.get_doc("LMS Course", course_name)
		doc.append("instructors", {"instructor": MENTOR_EMAIL})
		doc.save(ignore_permissions=True)

	if courses:
		frappe.db.commit()
