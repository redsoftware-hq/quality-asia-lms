"""Permission hooks to restrict the Accountant role's Desk surface.

The Accountant account (school@qualityasia.in) needs ``desk_access`` to view
LMS Payment records in Desk, but that inherits Frappe's baseline "Desk User"
read on doctypes like User, Communication, etc.  These hooks block access to
sensitive doctypes without touching Custom DocPerm — so they can't re-trigger
the perm-wipe that broke LMS Student enrollment (see QA-38 hotfix).

How it works:
  - ``permission_query_conditions`` returns ``"1=0"`` for list queries from
    an Accountant-only user → empty list, no data leaks.
  - ``has_permission`` returns ``False`` for single-doc reads → blocks
    form/API access to individual records.
"""

import frappe

# Doctypes the Accountant can legitimately access (via Custom DocPerm).
ALLOWED_DOCTYPES = {"LMS Payment", "Address"}


def _is_accountant_only():
	"""True when the session user's only elevated role is Accountant.

	Skips the ubiquitous roles (Guest, All, Desk User) so that a System Manager
	or Operations user is never affected by these restrictions."""
	if frappe.session.user in ("Administrator", "Guest"):
		return False
	roles = set(frappe.get_roles()) - {"Guest", "All", "Desk User"}
	return roles == {"Accountant"}


def user_query_conditions(user=None):
	"""permission_query_conditions for User doctype."""
	if _is_accountant_only():
		return "1=0"
	return ""


def user_has_permission(doc, ptype=None, user=None):
	"""has_permission for User doctype."""
	if _is_accountant_only():
		# Allow the user to read their own User doc (needed for session).
		if doc.name == frappe.session.user:
			return True
		return False
