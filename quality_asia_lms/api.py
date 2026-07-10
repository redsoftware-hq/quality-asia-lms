"""Public certificate verification API, consumed by the PHP corporate website.

The PHP site posts a certificate number (e.g. "IAC-07553") and gets back the
candidate/training details if it matches a real `LMS Certificate`, or a
"not found" response otherwise. It's a genuine DB lookup by doc name — the
IAC- prefix check below is just a cheap early rejection, not the real answer.

Guest-accessible by design (the PHP site has no Frappe login), so it's
rate-limited per IP to stop bulk enumeration of certificate numbers. Real
visitors verify a handful of certificates at most, so the limit is kept low.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

CERTIFICATE_PREFIX = "IAC-"


@frappe.whitelist(allow_guest=True)  # nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method
@rate_limit(limit=8, seconds=60)
def verify_certificate(certificate_number: str = ""):
	certificate_number = (certificate_number or "").strip().upper()

	if not certificate_number.startswith(CERTIFICATE_PREFIX):
		return {"status": "invalid", "message": _("Invalid certificate number")}

	if not frappe.db.exists("LMS Certificate", certificate_number):
		return {"status": "not_found", "message": _("Certificate not found")}

	cert = frappe.db.get_value(
		"LMS Certificate",
		certificate_number,
		["member_name", "candidate_name_as_printed", "course", "training_dates", "issue_date"],
		as_dict=True,
	)
	course_title = frappe.db.get_value("LMS Course", cert.course, "title") if cert.course else ""

	return {
		"status": "success",
		"certificate_number": certificate_number,
		"candidate_name": cert.candidate_name_as_printed or cert.member_name,
		"training_program": course_title,
		"training_dates": cert.training_dates,
		"date_of_issue": cert.issue_date,
	}
