"""Force India as the billing country during checkout + dedup pending payments.

The browser supplies `country` to both the order-summary (display) and the
payment-link (charge) endpoints, and that value gates the 18% GST in
`lms.lms.utils.apply_gst`. A tampered request with `country != "India"` would
therefore skip GST — a real tax/revenue leak, since the frontend dropdown can
be bypassed entirely (devtools / curl).

Quality Asia sells to India only, so we enforce `country = "India"` on the
SERVER for both endpoints, ignoring whatever the client sends. This guarantees
INR + 18% GST on what is actually charged, and keeps the displayed summary
consistent with the charge. App-owned + upgrade-safe (registered via
`override_whitelisted_methods` in hooks.py), like the Razorpay override.

Additionally, the upstream ``record_payment`` inside ``get_payment_link``
unconditionally creates a new ``LMS Payment`` on every call, so
re-opening / refreshing checkout accumulates orphaned unpaid rows. Before
delegating we delete any stale pending payment for the same member + document,
keeping at most one pending row per enrollment.
"""

import frappe
from lms.lms.payments import get_payment_link as _get_payment_link
from lms.lms.utils import get_order_summary as _get_order_summary

FORCED_COUNTRY = "India"


def _cleanup_pending_payments(doctype: str, docname: str):
	"""Delete orphaned unpaid LMS Payment rows for the current user + document.

	Called just before upstream ``get_payment_link`` creates a fresh row, so only
	one pending payment exists at a time. Only rows with ``payment_received=0``
	and no invoice are touched — paid/invoiced rows are never deleted.

	Wrapped in try/except so a cleanup failure never blocks checkout.
	"""
	try:
		stale = frappe.get_all(
			"LMS Payment",
			filters={
				"member": frappe.session.user,
				"payment_for_document_type": doctype,
				"payment_for_document": docname,
				"payment_received": 0,
				"invoice_number": ("is", "not set"),
			},
			pluck="name",
		)
		for name in stale:
			frappe.delete_doc("LMS Payment", name, ignore_permissions=True, force=True)
	except Exception:
		frappe.log_error(title="QA: cleanup_pending_payments failed (non-blocking)")


@frappe.whitelist()
def get_payment_link(
	doctype: str,
	docname: str,
	address: dict,
	payment_for_certificate: int,
	coupon_code: str | None = None,
	country: str | None = None,
):
	"""Charge path — enforce India so GST cannot be skipped by client input.

	Also removes stale pending payments before the upstream creates a new one,
	preventing the orphaned-row accumulation visible in LMS Payment list view.
	"""
	_cleanup_pending_payments(doctype, docname)
	return _get_payment_link(
		doctype,
		docname,
		address,
		payment_for_certificate,
		coupon_code=coupon_code,
		country=FORCED_COUNTRY,
	)


@frappe.whitelist()
def get_order_summary(doctype: str, docname: str, coupon: str | None = None, country: str | None = None):
	"""Display path — keep the shown summary identical to what will be charged."""
	return _get_order_summary(doctype, docname, coupon=coupon, country=FORCED_COUNTRY)
