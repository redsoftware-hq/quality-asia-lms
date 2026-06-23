"""QA-37: Invoice generation and email on LMS Payment success.

Generates a sequential invoice number (B2C/YY-YY/XXXXXX, Indian FY) when
payment_received flips to 1, then emails the rendered PDF to the learner.

Series format: B2C/<FY-start>-<FY-end>/<6-digit-seq>
Example:        B2C/26-27/000001
The sequence resets to 000001 on 1 April of each Indian financial year.

Wired via doc_events → LMS Payment → on_update in hooks.py.
"""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, money_in_words

INVOICE_PREFIX = "B2C"
HSN_SAC = "998311"
GST_RATE = 9


def generate_invoice_for_payment(payment_name):
	"""Reusable entry point — loads the LMS Payment and issues an invoice + email.

	Safe to call from anywhere (override, patch, bench execute). The guards
	inside on_payment_update make this fully idempotent: a payment that already
	has an invoice_number is skipped."""
	doc = frappe.get_doc("LMS Payment", payment_name)
	on_payment_update(doc)


def on_payment_update(doc, method=None):
	"""doc_event handler for LMS Payment.on_update.

	Fires only when payment_received is checked and no invoice_number exists yet.
	Generates the invoice number and enqueues the email asynchronously so the
	payment flow is never blocked.

	Also called directly via generate_invoice_for_payment() from the
	on_payment_authorized override (overrides/payment_doctypes.py), since the
	upstream payment-success path uses db.set_value and never triggers on_update.
	"""
	if not doc.payment_received:
		return
	if doc.get("invoice_number"):
		return

	invoice_number = _generate_invoice_number(doc)
	frappe.db.set_value(
		"LMS Payment", doc.name, "invoice_number", invoice_number, update_modified=False
	)
	doc.invoice_number = invoice_number

	# Pass invoice_number explicitly so the background job never reads a
	# stale DB row in the edge-case where the transaction hasn't committed yet
	# when the worker picks up the task.
	frappe.enqueue(
		_send_invoice_email,
		queue="short",
		payment_name=doc.name,
		invoice_number=invoice_number,
		enqueue_after_commit=True,
	)


def _indian_fy(dt):
	"""Return (start_year, end_year) for the Indian financial year containing dt."""
	d = getdate(dt)
	if d.month >= 4:
		return d.year, d.year + 1
	return d.year - 1, d.year


def _generate_invoice_number(doc):
	"""Generate B2C/YY-YY/XXXXXX for the current Indian FY (6-digit, resets 1 April)."""
	fy_start, fy_end = _indian_fy(doc.creation)
	prefix = f"{INVOICE_PREFIX}/{fy_start % 100:02d}-{fy_end % 100:02d}/"

	existing = frappe.db.sql(
		"""SELECT invoice_number FROM `tabLMS Payment`
		WHERE invoice_number LIKE %s""",
		(f"{prefix}%",),
		as_list=True,
	)
	max_seq = 0
	for (num,) in existing:
		try:
			seq = int(num.split("/")[-1])
			max_seq = max(max_seq, seq)
		except (ValueError, IndexError):
			pass

	return f"{prefix}{max_seq + 1:06d}"


def _send_invoice_email(payment_name, invoice_number=None):
	"""Render the invoice PDF and email it to the learner.

	``invoice_number`` is passed explicitly by the caller so that the job
	works correctly even when the background worker picks it up before the
	DB transaction that wrote the number has fully committed.
	"""
	try:
		doc = frappe.get_doc("LMS Payment", payment_name)
		# Prefer the explicitly supplied number; fall back to the DB value.
		inv_num = invoice_number or doc.invoice_number
		if not inv_num:
			frappe.log_error(
				title=f"QA Invoice email skipped for {payment_name}: no invoice_number"
			)
			return

		pdf = frappe.get_print(
			"LMS Payment", doc.name, print_format="QA Invoice", as_pdf=True
		)

		member_email = doc.member
		member_name = doc.billing_name or frappe.db.get_value("User", doc.member, "full_name") or ""
		course_title = ""
		if doc.payment_for_document:
			course_title = frappe.db.get_value(
				doc.payment_for_document_type, doc.payment_for_document, "title"
			) or doc.payment_for_document

		subject = _("Your Invoice {0} — Quality Asia School").format(inv_num)

		frappe.sendmail(
			recipients=member_email,
			subject=subject,
			message=_(
				"Hi {0},<br><br>"
				"Thank you for enrolling in <b>{1}</b>! "
				"Your tax invoice is attached for your records.<br><br>"
				"If you have any questions, just reply to this email.<br><br>"
				"Warm regards,<br>Quality Asia School"
			).format(member_name, course_title),
			attachments=[{"fname": f"Invoice-{inv_num.replace('/', '-')}.pdf", "fcontent": pdf}],
			header=[subject, "green"],
			now=True,
		)

		frappe.db.set_value(
			"LMS Payment", doc.name, "invoice_emailed", 1, update_modified=False
		)
	except Exception:
		frappe.log_error(title=f"QA Invoice email failed for {payment_name}")


def get_invoice_context(doc):
	"""Build template context for the QA Invoice print format."""
	from quality_asia_lms.overrides.certificate import qa_cert_image

	amount = float(doc.amount or 0)
	amount_with_gst = float(doc.amount_with_gst or 0)
	gst_total = amount_with_gst - amount if amount_with_gst > amount else 0
	cgst = gst_total / 2
	sgst = gst_total / 2

	course_title = ""
	if doc.payment_for_document:
		course_title = frappe.db.get_value(
			doc.payment_for_document_type, doc.payment_for_document, "title"
		) or doc.payment_for_document

	address_display = ""
	if doc.address:
		addr = frappe.get_doc("Address", doc.address)
		parts = [addr.address_line1, addr.address_line2, addr.city, addr.state, addr.pincode, addr.country]
		address_display = ", ".join(p for p in parts if p)

	return {
		"logo": qa_cert_image("logo.png"),
		"signature": qa_cert_image("signature.jpg"),
		"invoice_number": doc.invoice_number or "",
		"invoice_date": formatdate(getdate(doc.creation)),
		"billing_name": doc.billing_name or "",
		"billing_address": address_display,
		"billing_gstin": doc.gstin or "",
		"billing_pan": doc.pan or "",
		"course_title": course_title,
		"hsn_sac": HSN_SAC,
		"amount": amount,
		"cgst_rate": GST_RATE,
		"cgst_amount": cgst,
		"sgst_rate": GST_RATE,
		"sgst_amount": sgst,
		"total": amount_with_gst or amount,
		"discount": float(doc.discount_amount or 0),
		"total_in_words": money_in_words(amount_with_gst or amount, "INR"),
	}
