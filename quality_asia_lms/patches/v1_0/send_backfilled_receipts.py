"""QA-39: (Superseded) Email invoice receipts for backfilled payments.

This patch is now a no-op. Its logic (email receipts for paid rows with an
invoice_number but no invoice_emailed flag) was fully subsumed by the
``backfill_stranded_invoices`` patch (QA-50), which both assigns missing
invoice numbers AND sends receipts in a single pass.

The entry in ``patches.txt`` is retained so Frappe doesn't re-run it on
sites where it has already executed.
"""


def execute():
	pass
