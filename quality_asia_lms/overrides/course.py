"""LMS Course overrides.

Wired via ``doc_events`` → ``LMS Course`` → ``before_save`` and
``override_whitelisted_methods`` in hooks.py.
"""

import frappe
from lms.lms.utils import get_course_outline as _original_get_course_outline


@frappe.whitelist(allow_guest=True)
def get_course_outline(course: str = None, progress: bool = False):
	if not course:
		return []
	return _original_get_course_outline(course, progress)


def sync_paid_category(doc, method=None):
	if doc.paid_course and doc.category != "Paid":
		if frappe.db.exists("LMS Category", "Paid"):
			doc.category = "Paid"
	elif not doc.paid_course and doc.category == "Paid":
		if frappe.db.exists("LMS Category", "Free"):
			doc.category = "Free"
