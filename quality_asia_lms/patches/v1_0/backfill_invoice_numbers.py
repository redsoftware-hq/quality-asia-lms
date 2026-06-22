"""Backfill invoice_number on existing LMS Payments that have payment_received=1 but no number."""

import frappe


def execute():
	from quality_asia_lms.overrides.invoice import _generate_invoice_number

	payments = frappe.get_all(
		"LMS Payment",
		filters={"payment_received": 1, "invoice_number": ("in", ["", None])},
		fields=["name", "creation"],
		order_by="creation asc",
	)
	for p in payments:
		doc = frappe.get_doc("LMS Payment", p.name)
		inv = _generate_invoice_number(doc)
		frappe.db.set_value("LMS Payment", p.name, "invoice_number", inv, update_modified=False)

	if payments:
		frappe.db.commit()
