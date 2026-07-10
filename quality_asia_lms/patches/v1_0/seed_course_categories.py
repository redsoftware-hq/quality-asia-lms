"""QA-31: Seed course categories (Free, Paid, Introduction) and backfill.

LMS already ships the ``LMS Category`` doctype and a ``category`` Link field on
``LMS Course``.  This patch creates the three categories, maps existing courses
(paid_course=1 → Paid, else Free), and sets Introduction as the default for new
courses via a Property Setter.

Idempotent — safe to re-run.
"""

import frappe


CATEGORIES = ["Free", "Paid", "Introduction"]
DEFAULT_CATEGORY = "Introduction"


def execute():
	for cat in CATEGORIES:
		if not frappe.db.exists("LMS Category", cat):
			frappe.get_doc({"doctype": "LMS Category", "category": cat}).insert(ignore_permissions=True)

	courses = frappe.get_all("LMS Course", fields=["name", "paid_course", "category"])
	for c in courses:
		if c.category:
			continue
		target = "Paid" if c.paid_course else "Free"
		frappe.db.set_value("LMS Course", c.name, "category", target, update_modified=False)

	ps_name = "LMS Course-main-category-default"
	if not frappe.db.exists("Property Setter", ps_name):
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"name": ps_name,
				"doctype_or_field": "DocField",
				"doc_type": "LMS Course",
				"field_name": "category",
				"property": "default",
				"value": DEFAULT_CATEGORY,
				"property_type": "Small Text",
			}
		).insert(ignore_permissions=True)

	frappe.db.commit()
