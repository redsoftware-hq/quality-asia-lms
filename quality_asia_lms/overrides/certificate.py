"""Quality Asia certificate customizations on top of stock LMS Certificate.

  - Every generated certificate is forced onto our print format ("QA Certificate")
    and renders in the Quality Asia School format.
  - Two training dates are auto-filled relative to the issue date and shown on the
    certificate as e.g. "07th, 08th APRIL 2026".
  - The "Congratulations on getting certified!" email carries the certificate PDF
    as an in-memory attachment (QALMSCertificate, wired via override_doctype_class).

Shipped entirely as code (fixtures + these hooks) so it survives `bench migrate`
and a fresh deploy — no fork of the LMS app.
"""

import base64
import mimetypes

import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate
from lms.lms.doctype.lms_certificate.lms_certificate import LMSCertificate

QA_TEMPLATE = "QA Certificate"
IAC_PREFIX = "IAC-"
_IAC_NUM_RE = re.compile(r"IAC\s*-\s*0*(\d+)", re.IGNORECASE)

# Training runs over two consecutive days; the first day sits 15 days before the
# certificate's issue date (client rule, 2026-06-10). To shift the window, change
# only these two offsets.
TRAINING_START_OFFSET = -15
TRAINING_END_OFFSET = -14


def prepare_certificate(doc, method=None):
	"""before_insert on LMS Certificate: pin our print format and fill the dates."""
	if frappe.db.exists("Print Format", QA_TEMPLATE):
		doc.template = QA_TEMPLATE
	populate_training_dates(doc)


def populate_training_dates(doc):
	"""Auto-fill the two training dates from issue_date, only when blank so a
	manual override is never clobbered."""
	if not doc.issue_date:
		return
	issue = getdate(doc.issue_date)
	if not doc.get("training_start_date"):
		doc.training_start_date = add_days(issue, TRAINING_START_OFFSET)
	if not doc.get("training_end_date"):
		doc.training_end_date = add_days(issue, TRAINING_END_OFFSET)


def enforce_qa_certificate_template():
	"""after_migrate: bring every existing certificate onto the QA format + dates.

	Runs after fixtures are synced (so the print format already exists). Idempotent
	— only touches rows not already on the QA template."""
	if not frappe.db.exists("Print Format", QA_TEMPLATE):
		return
	names = frappe.get_all(
		"LMS Certificate", filters={"template": ["!=", QA_TEMPLATE]}, pluck="name"
	)
	for name in names:
		doc = frappe.get_doc("LMS Certificate", name)
		doc.template = QA_TEMPLATE
		populate_training_dates(doc)
		doc.save(ignore_permissions=True)
	if names:
		frappe.db.commit()


def qa_cert_image(filename):
	"""Return a base64 data URI for a certificate image shipped in the app.

	The print format embeds images inline rather than linking `/assets/...` because
	the PDF engine (wkhtmltopdf) cannot reliably fetch them over the network during
	rendering. Reading the file at print time keeps the images as real, swappable
	files in the repo."""
	path = frappe.get_app_path("quality_asia_lms", "public", "images", "qa-cert", filename)
	try:
		with open(path, "rb") as f:
			data = base64.b64encode(f.read()).decode()
	except OSError:
		frappe.log_error(title=f"QA Certificate: missing image {filename}")
		return ""
	mime = mimetypes.guess_type(filename)[0] or "image/jpeg"
	return f"data:{mime};base64,{data}"


def _ordinal(day):
	suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
	return f"{day:02d}{suffix}"


def format_training_dates(start, end):
	"""Jinja helper for the print format. Renders the two training dates as
	'07th, 08th APRIL 2026', collapsing the month/year when shared and expanding
	them only when the range crosses a boundary."""
	if not start or not end:
		return ""
	start, end = getdate(start), getdate(end)
	if (start.year, start.month) == (end.year, end.month):
		return f"{_ordinal(start.day)}, {_ordinal(end.day)} {start.strftime('%B').upper()} {start.year}"
	if start.year == end.year:
		return (
			f"{_ordinal(start.day)} {start.strftime('%B').upper()}, "
			f"{_ordinal(end.day)} {end.strftime('%B').upper()} {end.year}"
		)
	return (
		f"{_ordinal(start.day)} {start.strftime('%B').upper()} {start.year}, "
		f"{_ordinal(end.day)} {end.strftime('%B').upper()} {end.year}"
	)


def _next_iac_number():
	"""Return the next available IAC sequence number.

	Scans all existing LMS Certificate names that match the IAC pattern
	(including the 135 space-variant ``IAC -XXXXX`` rows from the DWM migration)
	and returns max + 1."""
	all_names = frappe.db.sql_list("SELECT name FROM `tabLMS Certificate`")
	max_num = 0
	for name in all_names:
		m = _IAC_NUM_RE.match(name)
		if m:
			max_num = max(max_num, int(m.group(1)))
	return max_num + 1


class QALMSCertificate(LMSCertificate):
	"""Stock LMS Certificate with QA customizations.

	Wired via ``override_doctype_class``.

	Customizations:
	  - ``autoname``: continues the DWM ``IAC-XXXXX`` series so new and legacy
	    certificates share a single, gap-free numbering convention.  The DWM
	    migration path (``set_name=old_id``) bypasses autoname entirely.
	  - ``send_mail``: attaches the certificate PDF to the congratulations email.
	"""

	def autoname(self):
		"""Generate the next IAC-XXXXX name, skipping any that already exist."""
		next_num = _next_iac_number()
		while True:
			candidate = f"{IAC_PREFIX}{next_num:05d}"
			if not frappe.db.exists("LMS Certificate", candidate):
				self.name = candidate
				return
			next_num += 1

	def send_mail(self):
		from frappe.email.doctype.email_template.email_template import get_email_template

		subject = _("Congratulations! Your training certificate is ready")
		template = "certification"
		custom_template = frappe.db.get_single_value("LMS Settings", "certification_template")

		args = {
			"member_name": self.member_name,
			"course_name": self.course,
			"course_title": frappe.db.get_value("LMS Course", self.course, "title"),
			"name": self.name,
			"template": self.template,
		}

		content = None
		if custom_template:
			email_template = get_email_template(custom_template, args)
			subject = email_template.get("subject")
			content = email_template.get("message")

		frappe.sendmail(
			recipients=self.member,
			subject=subject,
			template=template if not custom_template else None,
			content=content if custom_template else None,
			args=args,
			header=[subject, "green"],
			attachments=self._certificate_pdf_attachment(),
		)

	def _certificate_pdf_attachment(self):
		"""Render the certificate as an in-memory PDF for the email.

		The PDF is built with ``frappe.get_print(..., as_pdf=True)`` and passed
		inline to ``frappe.sendmail`` — no File record is created, so it consumes
		no disk/object storage (it lives only in the auto-cleared Email Queue row).
		Returns [] on any render failure so a PDF error never blocks the email.
		"""
		try:
			pdf = frappe.get_print(
				"LMS Certificate", self.name, print_format=self.template, as_pdf=True
			)
		except Exception:
			frappe.log_error(title=f"QA cert email: PDF render failed for {self.name}")
			return []

		base = frappe.scrub(self.member_name or self.name) or "certificate"
		return [{"fname": f"{base}_certificate.pdf", "fcontent": pdf}]
