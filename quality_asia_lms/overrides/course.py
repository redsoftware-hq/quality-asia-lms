"""LMS Course overrides.

Wired via ``doc_events`` → ``LMS Course`` → ``before_save`` and
``override_whitelisted_methods`` in hooks.py.
"""

import re
from urllib.parse import urlparse

import frappe
from lms.lms.utils import get_course_outline as _original_get_course_outline


def _course_from_referer():
	"""Recover the course docname from the Referer URL.

	The upstream Vue SPA fires ``get_course_outline`` with ``auto: true``
	before the parent ``course`` resource resolves for non-admin users
	(students / guests).  The request arrives with ``course=undefined``
	(i.e. missing), but the browser sends the full page path as Referer
	(same-origin, default referrer policy).  The slug after ``/courses/``
	is the ``LMS Course.name`` (set by ``generate_slug`` in ``autoname``).
	"""
	try:
		referer = frappe.request.headers.get("Referer") if frappe.request else None
	except Exception:
		referer = None
	if not referer:
		return None
	path = urlparse(referer).path  # e.g. /lms/courses/<slug>[/lesson/…]
	m = re.search(r"/courses/([^/?#]+)", path)
	if not m:
		return None
	slug = m.group(1)
	if frappe.db.exists("LMS Course", slug):
		return slug
	return None


@frappe.whitelist(allow_guest=True)
def get_course_outline(course: str = None, progress: bool = False):
	if not course:
		course = _course_from_referer()
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
