"""Auto-assign the default mentor/instructor on new LMS Course creation.

Wired via ``doc_events`` → ``LMS Course`` → ``before_insert`` in hooks.py.
"""

import frappe

MENTOR_EMAIL = "samarth@qualityasia.in"


def auto_assign_mentor(doc, method=None):
	if not frappe.db.exists("User", MENTOR_EMAIL):
		return
	existing = [row.instructor for row in (doc.get("instructors") or [])]
	if MENTOR_EMAIL not in existing:
		doc.append("instructors", {"instructor": MENTOR_EMAIL})
