"""Auto-sync LMS Course category with paid_course flag.

Wired via ``doc_events`` → ``LMS Course`` → ``before_save`` in hooks.py.
"""

import frappe


def sync_paid_category(doc, method=None):
	if doc.paid_course and doc.category != "Paid":
		if frappe.db.exists("LMS Category", "Paid"):
			doc.category = "Paid"
	elif not doc.paid_course and doc.category == "Paid":
		if frappe.db.exists("LMS Category", "Free"):
			doc.category = "Free"
