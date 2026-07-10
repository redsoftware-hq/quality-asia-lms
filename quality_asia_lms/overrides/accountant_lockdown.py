"""Accountant role lockdown — permission hooks + auto-configuration.

Any user assigned the Accountant role is automatically restricted:

1. ``enforce_accountant_lockdown`` (User validate hook) — strips every role
   except Accountant so LMS app tiles disappear and only the Finance workspace
   is reachable.  Also pins ``default_workspace`` and ``default_app``.  Runs on
   every User save, so adding the Accountant role in Desk is all that's needed.

2. ``user_query_conditions`` / ``user_has_permission`` (permission hooks) —
   block access to the User list and individual User docs (except own record).
   Uses runtime role checks, NOT Custom DocPerm, so it can't re-trigger the
   perm-wipe that broke LMS Student enrollment (see QA-38 hotfix).
"""

import frappe

# Doctypes the Accountant can legitimately access (via Custom DocPerm).
ALLOWED_DOCTYPES = {"LMS Payment", "Address"}

# Roles that Frappe auto-grants to every user — never try to strip these.
_AUTO_ROLES = frozenset({"All", "Guest", "Desk User"})
_KEEP_ROLES = frozenset({"Accountant"})


def enforce_accountant_lockdown(doc, method=None):
	"""``validate`` hook for User — auto-lockdown when Accountant role is present.

	Strips non-Accountant roles so LMS tiles disappear, and pins the Finance
	workspace.  Works for any user assigned the role — no hardcoded emails.
	"""
	user_roles = {r.role for r in doc.roles}
	if "Accountant" not in user_roles:
		return

	to_remove = user_roles - _KEEP_ROLES - _AUTO_ROLES
	if to_remove:
		doc.roles = [r for r in doc.roles if r.role not in to_remove]

	doc.default_workspace = "Finance"
	doc.default_app = ""


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
		if doc.name == frappe.session.user:
			return True
		return False
