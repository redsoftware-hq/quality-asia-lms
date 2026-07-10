"""QA-50: Backfill invoice numbers and email receipts for stranded payments.

Payments created after the original backfill patches (QA-38/39) ran were left
without an invoice_number (and hence without a receipt email) because the live
on_update doc_event never fires — upstream sets payment_received via
db.set_value, bypassing the document lifecycle.

This patch:
1. Assigns the next sequential B2C invoice number to every LMS Payment with
   payment_received=1 but no invoice_number.
2. Enqueues the receipt email for every LMS Payment that now has an
   invoice_number but has not yet been emailed.

Idempotent — safe to re-run. The invoice number guard and the invoice_emailed
flag prevent duplicates.
"""

import frappe


BATCH_SIZE = 20


def execute():
	from quality_asia_lms.overrides.invoice import _generate_invoice_number, _send_invoice_email

	# --- Phase 1: assign missing invoice numbers ---
	missing_number = frappe.get_all(
		"LMS Payment",
		filters={
			"payment_received": 1,
			"invoice_number": ["in", ["", None]],
		},
		fields=["name", "creation"],
		order_by="creation asc",
	)
	for p in missing_number:
		doc = frappe.get_doc("LMS Payment", p.name)
		inv = _generate_invoice_number(doc)
		frappe.db.set_value("LMS Payment", p.name, "invoice_number", inv, update_modified=False)

	if missing_number:
		frappe.db.commit()
		frappe.logger("qa_lms").info(
			f"backfill_stranded_invoices: assigned {len(missing_number)} invoice numbers"
		)

	# --- Phase 2: email receipts that haven't been sent yet ---
	unsent = frappe.get_all(
		"LMS Payment",
		filters={
			"payment_received": 1,
			"invoice_number": ["is", "set"],
			"invoice_emailed": ["in", [0, None, ""]],
		},
		fields=["name", "invoice_number"],
		order_by="creation asc",
	)

	for i, p in enumerate(unsent):
		frappe.enqueue(
			_send_invoice_email,
			queue="short",
			user="Administrator",
			payment_name=p.name,
			invoice_number=p.invoice_number,
			enqueue_after_commit=True,
		)
		if (i + 1) % BATCH_SIZE == 0:
			frappe.db.commit()

	if unsent:
		frappe.db.commit()
		frappe.logger("qa_lms").info(
			f"backfill_stranded_invoices: enqueued {len(unsent)} invoice emails"
		)
