"""One-time patch: delete orphaned unpaid LMS Payment rows.

Upstream ``record_payment`` creates a new ``LMS Payment`` on every checkout
initiation with no dedup, so re-opening / refreshing checkout accumulates
unpaid rows. This patch removes confirmed orphans: rows where
``payment_received=0`` with no invoice number, but a *paid* sibling exists
for the same member + document (proof that the enrollment was completed via
another row). Genuinely-pending standalone rows are left alone.
"""

import frappe


def execute():
	# Find all paid (member, doc_type, doc_name) combos
	paid = frappe.db.sql(
		"""
		SELECT DISTINCT member, payment_for_document_type, payment_for_document
		FROM `tabLMS Payment`
		WHERE payment_received = 1
		""",
		as_dict=True,
	)

	deleted = 0
	for row in paid:
		orphans = frappe.get_all(
			"LMS Payment",
			filters={
				"member": row.member,
				"payment_for_document_type": row.payment_for_document_type,
				"payment_for_document": row.payment_for_document,
				"payment_received": 0,
				"invoice_number": ("is", "not set"),
			},
			pluck="name",
		)
		for name in orphans:
			frappe.delete_doc("LMS Payment", name, ignore_permissions=True, force=True)
			deleted += 1

	if deleted:
		frappe.db.commit()
		print(f"[quality_asia_lms] Cleaned up {deleted} orphaned unpaid LMS Payment row(s)")
