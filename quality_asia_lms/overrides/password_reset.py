import frappe
from frappe import _
from frappe.core.doctype.user.user import User
from frappe.rate_limiter import rate_limit
from frappe.utils.password import get_password_reset_limit


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=get_password_reset_limit, seconds=60 * 60)
def reset_password(user: str) -> None:
	try:
		user_doc: User = frappe.get_doc("User", user)
		if user_doc.name != "Administrator" and user_doc.enabled:
			user_doc.validate_reset_password()
			user_doc._reset_password(send_email=True)
	except frappe.DoesNotExistError:
		frappe.clear_messages()
	except frappe.OutgoingEmailError:
		frappe.clear_messages()
		frappe.log_error(title="Password reset email could not be sent", message=frappe.get_traceback())
	except Exception:
		frappe.clear_messages()
		frappe.log_error(title="Password reset failed unexpectedly", message=frappe.get_traceback())

	frappe.msgprint(
		msg=_(
			"We've sent a password reset link to your email address."
			" Please check your inbox and spam folder. The link will expire in a few minutes."
		),
		title=_("Check Your Email"),
	)
