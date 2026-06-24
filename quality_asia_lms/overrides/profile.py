"""Backend for the extra profile fields (mobile, address, resume) that we add to
the LMS portal's Edit Profile modal via injected JS (QA-15).

These run server-side in our app, so they're robust and deploy cleanly on Frappe
Cloud; only the modal UI that calls them is injected into the SPA. Each method is
scoped to the *logged-in* user — a website user can only read/write their own
profile.
"""

import frappe
from frappe import _

from quality_asia_lms.overrides.signup import _validate_mobile

EXTRA_FIELDS = ("mobile_no", "address", "resume")


def _require_user():
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please log in to update your profile."), frappe.PermissionError)
	return user


@frappe.whitelist()
def get_profile_extras():
	"""Current values, to pre-fill the injected modal fields. Includes the email
	(read-only in the UI — it's the login id and isn't editable here)."""
	return frappe.db.get_value("User", _require_user(), ("email",) + EXTRA_FIELDS, as_dict=True) or {}


@frappe.whitelist()
def update_profile_extras(mobile_no=None, address=None, resume=None):
	"""Save the QA-specific profile fields for the logged-in user.

	Only the fields passed (non-None) are touched, so the injected UI can save
	independently of the stock modal's own save. Mobile, when provided, is
	validated with the same lenient rule as signup.
	"""
	user = _require_user()
	values = {}

	if mobile_no is not None:
		mobile_no = mobile_no.strip()
		if mobile_no:
			_validate_mobile(mobile_no)
		values["mobile_no"] = mobile_no
	if address is not None:
		values["address"] = address.strip()
	if resume is not None:
		# resume is the file_url returned by the upload; "" clears it.
		values["resume"] = resume.strip()

	if values:
		frappe.db.set_value("User", user, values)
	return values
