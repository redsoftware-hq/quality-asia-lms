"""Custom self-signup for the Quality Asia portal.

Frappe's /login#signup page renders the template returned by the
`signup_form_template` hook (it uses the last app's value). Because this app
loads after `lms`, `get_signup_template` below overrides the stock/LMS signup
form with no fork of either app.

The form collects mandatory Name, Email and Mobile Number, plus optional Company
Name, Residential Address, Profile Photo and Resume/CV.  A random password is
set internally and a welcome email with a password-reset link is sent so the
user can set their own password on first login.

Existing-user detection (D3): if the email is already registered, the signup
returns a friendly message directing the user to reset their password.

The signup page is served to guests, so the two file uploads can't use the
login-only `/api/method/upload_file` endpoint that the Edit Profile modal (QA-15)
uses. Instead the form posts the files as base64 inside this same `sign_up` call;
they're decoded, size/type-checked and saved here only once the User is created —
so the rate limit below also caps file writes and there's no abusable guest upload.
"""

import base64
import os
import re

import frappe
from frappe import _
from frappe.utils import cint, escape_html, random_string
from frappe.utils.file_manager import save_file
from frappe.website.utils import is_signup_disabled

ALLOWED_MOBILE_CHARS = re.compile(r"^[+0-9\s\-]+$")

# Keep uploads small so the DB/attachments don't bloat from self-signups.
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_RESUME_EXT = {".pdf", ".doc", ".docx"}
MAX_PHOTO_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB


def get_signup_template():
	"""`signup_form_template` hook → our signup form."""
	return "quality_asia_lms/templates/signup-form.html"


def _validate_mobile(mobile_no):
	"""Lenient phone check: only +, digits, spaces, hyphens, 7-15 digits total.
	Accepts Indian and international numbers; rejects junk and empty."""
	if not mobile_no:
		frappe.throw(_("Please provide your mobile number so we can reach you."))
	if not ALLOWED_MOBILE_CHARS.match(mobile_no):
		frappe.throw(_("That doesn't look like a valid phone number. Please check and try again."))
	digits = re.sub(r"\D", "", mobile_no)
	if not (7 <= len(digits) <= 15):
		frappe.throw(_("That doesn't look like a valid phone number. Please check and try again."))


def _save_signup_file(filename, b64, user_name, allowed_ext, max_bytes, is_private):
	"""Decode an optional base64 upload from the signup form, validate its type and
	size, and attach it to the freshly created User. Returns the file_url or None."""
	filename = (filename or "").strip()
	b64 = (b64 or "").strip()
	if not filename or not b64:
		return None

	ext = os.path.splitext(filename)[1].lower()
	if ext not in allowed_ext:
		frappe.throw(_("Sorry, {0} isn't a supported file type. Please upload a different format.").format(escape_html(filename)))

	try:
		content = base64.b64decode(b64, validate=True)
	except Exception:
		frappe.throw(_("We couldn't read the uploaded file. Please try again with a different file."))

	if not content:
		return None
	if len(content) > max_bytes:
		frappe.throw(_("The file {0} is too large. Please upload a smaller file.").format(escape_html(filename)))

	# save_file runs Frappe's own content checks (e.g. it rejects PDFs containing
	# JavaScript and can't parse corrupt files). Surface those as a clean message
	# instead of a raw server error — the request rolls back, so no half-made user.
	try:
		file_doc = save_file(filename, content, "User", user_name, decode=False, is_private=is_private)
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.clear_last_message()
		frappe.throw(_("We couldn't save {0}. Please try uploading a different file.").format(escape_html(filename)))
	return file_doc.file_url


@frappe.whitelist(allow_guest=True)  # nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method
def sign_up(
	email: str,
	full_name: str,
	mobile_no: str,
	company_name: str = "",
	address: str = "",
	photo_filename: str = "",
	photo_content: str = "",
	resume_filename: str = "",
	resume_content: str = "",
):
	if is_signup_disabled():
		frappe.throw(_("Registration is currently closed. Please check back later."), _("Registration Closed"))

	email = (email or "").strip()
	full_name = (full_name or "").strip()
	mobile_no = (mobile_no or "").strip()
	company_name = (company_name or "").strip()
	address = (address or "").strip()

	if not full_name or not email:
		frappe.throw(_("Please provide your name and email address to sign up."))
	_validate_mobile(mobile_no)

	user = frappe.db.get("User", {"email": email})
	if user:
		if user.enabled:
			return 0, _("It looks like you already have an account with Quality Asia School. Just reset your password to log in!")
		# Disabled account (usually a placeholder-email migrated user).
		# Don't suggest password reset — Frappe silently skips disabled users.
		return 2, _("It looks like you already have an account with Quality Asia School, but it needs to be activated. Please reach out to us at trainings@qualityasia.in and we'll get you set up.")

	max_signups = cint(frappe.get_system_settings("max_signups_allowed_per_hour") or 300)
	if frappe.db.get_creation_count("User", 60) >= max_signups:
		frappe.respond_as_web_page(
			_("Please Try Again Later"),
			_(
				"We're experiencing a high volume of sign-ups right now. Please try again in about an hour."
			),
			http_status_code=429,
		)
		return 0, _("Too many sign-ups right now. Please try again in about an hour.")

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": escape_html(full_name),
			"mobile_no": mobile_no,
			"company_name": company_name,
			"address": address,
			"country": "",
			"enabled": 1,
			"new_password": random_string(10),
			"send_welcome_email": 1,
			"user_type": "Website User",
			"default_app": "lms",
		}
	)
	user.flags.ignore_permissions = True
	user.flags.ignore_password_policy = True
	user.insert()

	# Same role assignment as the stock LMS signup.
	default_role = frappe.db.get_single_value("Portal Settings", "default_role")
	if default_role:
		user.add_roles(default_role)
	user.add_roles("LMS Student")

	# Best-effort country from IP, like LMS — never block signup if it fails.
	try:
		from lms.lms.user import set_country_from_ip

		set_country_from_ip(None, user.name)
	except Exception:
		frappe.clear_last_message()

	# Optional uploads: attach to the new User last (no user.save() runs after this,
	# so the db.set_value below can't trip the stale-timestamp check). Photo is public
	# (shown as the avatar); resume is private. A bad file surfaces a clean error and
	# rolls back the whole request rather than leaving a half-made account.
	file_values = {}
	photo_url = _save_signup_file(
		photo_filename, photo_content, user.name, ALLOWED_PHOTO_EXT, MAX_PHOTO_BYTES, is_private=0
	)
	if photo_url:
		file_values["user_image"] = photo_url
	resume_url = _save_signup_file(
		resume_filename, resume_content, user.name, ALLOWED_RESUME_EXT, MAX_RESUME_BYTES, is_private=1
	)
	if resume_url:
		file_values["resume"] = resume_url
	if file_values:
		frappe.db.set_value("User", user.name, file_values)

	return 1, _("Welcome aboard! We've sent you an email — please check your inbox to set your password and get started.")
