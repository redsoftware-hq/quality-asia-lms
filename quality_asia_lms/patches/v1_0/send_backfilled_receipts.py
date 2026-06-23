"""QA-39: Email invoice receipts for payments that were backfilled but never emailed.

The backfill_invoice_numbers patch (QA-38) populated invoice_number on historical
LMS Payment records, but the on_update handler only fires on new transitions to
payment_received=1. So those already-paid payments never got their receipt PDF.

This patch finds all LMS Payment rows where:
- payment_received = 1
- invoice_number IS SET
- invoice_emailed IS NOT SET (0 or null)

…and enqueues the existing _send_invoice_email job for each, in batches, so the
single background worker isn't overwhelmed.

Idempotent — _send_invoice_email sets invoice_emailed=1 on success, so re-running
skips already-emailed payments.
"""

import frappe


BATCH_SIZE = 20  # enqueue this many at a time to avoid choking the worker


def execute():
	payments = frappe.get_all(
		"LMS Payment",
		filters={
			"payment_received": 1,
			"invoice_number": ["is", "set"],
			"invoice_emailed": ["in", [0, None, ""]],
		},
		fields=["name", "invoice_number"],
		order_by="creation asc",
	)

	if not payments:
		frappe.logger("qa_lms").info("send_backfilled_receipts: nothing to send")
		return

	from quality_asia_lms.overrides.invoice import _send_invoice_email

	for i, p in enumerate(payments):
		frappe.enqueue(
			_send_invoice_email,
			queue="short",
			user="Administrator",
			payment_name=p.name,
			invoice_number=p.invoice_number,
			enqueue_after_commit=True,
		)
		# Commit in batches so enqueued jobs become visible to the worker
		if (i + 1) % BATCH_SIZE == 0:
			frappe.db.commit()

	frappe.db.commit()
	frappe.logger("qa_lms").info(
		f"send_backfilled_receipts: enqueued {len(payments)} invoice emails"
	)
