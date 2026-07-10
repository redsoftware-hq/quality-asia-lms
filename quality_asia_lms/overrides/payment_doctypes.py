"""QA-50: Issue invoice + email when Razorpay/Stripe confirms payment.

The upstream LMS sets ``payment_received`` via ``frappe.db.set_value``, which
bypasses the document lifecycle — so the QA ``on_update`` doc_event on
``LMS Payment`` never fires for real payments.  These doctype-class overrides
intercept ``on_payment_authorized`` (called by the *payments* app for every
gateway) and trigger invoice generation after the parent has completed
enrollment.

Registered via ``override_doctype_class`` in ``hooks.py`` — upgrade-safe, no
upstream files edited.
"""

import json

import frappe
from lms.lms.doctype.lms_batch.lms_batch import LMSBatch as _LMSBatch
from lms.lms.doctype.lms_course.lms_course import LMSCourse as _LMSCourse
from lms.lms.utils import get_integration_requests

from quality_asia_lms.overrides.invoice import generate_invoice_for_payment


def _issue_invoice(doctype, docname):
	"""Resolve the payment that was just authorised and generate its invoice.

	Uses the same Integration Request lookup that upstream's
	``update_payment_record`` relies on, so we always target the correct
	``LMS Payment`` row.
	"""
	try:
		reqs = get_integration_requests(doctype, docname)
		if not reqs:
			return
		data = frappe._dict(json.loads(reqs[0].data))
		if data.get("payment"):
			generate_invoice_for_payment(data.payment)
	except Exception:
		# Never let an invoice/email failure block enrollment.
		frappe.log_error(title=f"QA Invoice generation failed after payment for {doctype} {docname}")


class QALMSCourse(_LMSCourse):
	"""LMS Course with post-payment invoice generation."""

	def on_payment_authorized(self, payment_status):
		super().on_payment_authorized(payment_status)
		if payment_status in ("Authorized", "Completed"):
			_issue_invoice("LMS Course", self.name)


class QALMSBatch(_LMSBatch):
	"""LMS Batch with post-payment invoice generation."""

	def on_payment_authorized(self, payment_status):
		super().on_payment_authorized(payment_status)
		if payment_status in ("Authorized", "Completed"):
			_issue_invoice("LMS Batch", self.name)
