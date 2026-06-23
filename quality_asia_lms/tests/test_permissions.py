"""Regression tests for Custom DocPerm safety.

QA-38 root cause: inserting Custom DocPerm rows WITHOUT first cloning the
doctype's standard DocPerm entries makes Frappe discard ALL standard perms —
silently stripping roles like LMS Student from critical doctypes.

These tests assert that the standard roles still hold their expected permissions
on the affected doctypes.  If a future patch inserts Custom DocPerm without
calling ``frappe.permissions.setup_custom_perms`` first, these tests will fail.
"""

import unittest

import frappe


def _get_active_perms(doctype):
	"""Return the permission table rows Frappe actually uses for *doctype*.

	Frappe uses Custom DocPerm when ANY Custom DocPerm row exists for the
	doctype; otherwise it falls back to the standard DocPerm table.
	"""
	if frappe.db.exists("Custom DocPerm", {"parent": doctype}):
		return frappe.get_all(
			"Custom DocPerm",
			filters={"parent": doctype},
			fields=["role", "permlevel", "read", "write", "create", "delete", "print", "email", "export", "if_owner"],
		)
	return frappe.get_all(
		"DocPerm",
		filters={"parent": doctype},
		fields=["role", "permlevel", "read", "write", "create", "delete", "print", "email", "export", "if_owner"],
	)


def _role_perm(perms, role, permlevel=0):
	"""Extract the permission row for *role* at *permlevel*, or None."""
	for p in perms:
		if p.role == role and p.permlevel == permlevel:
			return p
	return None


class TestLMSStudentPermsIntact(unittest.TestCase):
	"""Verify that LMS Student keeps every permission the upstream LMS defines.

	Frappe ignores standard DocPerm once ANY Custom DocPerm exists for a
	doctype.  For each LMS Student standard permission on a doctype that has
	Custom DocPerm, we assert the equivalent Custom DocPerm row exists with
	the same flags — proving our Custom DocPerm inserts didn't wipe it.
	"""

	PERM_FLAGS = ("read", "write", "create", "delete")

	@classmethod
	def setUpClass(cls):
		cls.student_standard = frappe.get_all(
			"DocPerm",
			filters={"role": "LMS Student"},
			fields=["parent", "permlevel", "read", "write", "create", "delete", "if_owner"],
		)
		cls.doctypes_with_custom = {
			r["parent"]
			for r in frappe.get_all("Custom DocPerm", fields=["parent"], distinct=True)
		}

	def test_student_perms_not_wiped_by_custom_docperm(self):
		"""For every LMS Student standard perm on a Custom-DocPerm doctype,
		the matching Custom DocPerm row must exist with equal-or-greater flags."""
		missing = []
		weakened = []

		for std in self.student_standard:
			dt = std.parent
			if dt not in self.doctypes_with_custom:
				continue

			custom_row = frappe.db.get_value(
				"Custom DocPerm",
				{"parent": dt, "role": "LMS Student", "permlevel": std.permlevel},
				self.PERM_FLAGS + ("if_owner",),
				as_dict=True,
			)

			if not custom_row:
				missing.append(f"{dt} [L{std.permlevel}]")
				continue

			for flag in self.PERM_FLAGS:
				if std.get(flag) and not custom_row.get(flag):
					weakened.append(f"{dt} [L{std.permlevel}]: lost {flag}")

		msgs = []
		if missing:
			msgs.append(f"LMS Student rows MISSING from Custom DocPerm: {missing}")
		if weakened:
			msgs.append(f"LMS Student permissions WEAKENED: {weakened}")
		self.assertFalse(msgs, "\n".join(msgs))


class TestAccountantPerms(unittest.TestCase):
	"""Verify the Accountant role is scoped to read-only on LMS Payment."""

	def test_accountant_can_read_lms_payment(self):
		perms = _get_active_perms("LMS Payment")
		row = _role_perm(perms, "Accountant")
		self.assertIsNotNone(row, "Accountant has no permission row for LMS Payment")
		self.assertTrue(row.read, "Accountant lost read on LMS Payment")

	def test_accountant_cannot_write_lms_payment(self):
		perms = _get_active_perms("LMS Payment")
		row = _role_perm(perms, "Accountant")
		if row is None:
			self.skipTest("Accountant role not yet seeded")
		self.assertFalse(row.write, "Accountant should NOT have write on LMS Payment")
		self.assertFalse(row.create, "Accountant should NOT have create on LMS Payment")
		self.assertFalse(row.delete, "Accountant should NOT have delete on LMS Payment")


class TestAccountantLockdownHook(unittest.TestCase):
	"""Verify the User.validate hook auto-locks down Accountant users."""

	def test_hook_strips_non_accountant_roles(self):
		from quality_asia_lms.overrides.accountant_lockdown import enforce_accountant_lockdown

		user = frappe.get_doc({
			"doctype": "User",
			"email": "__test_acct_hook@example.com",
			"first_name": "Test",
			"user_type": "System User",
			"send_welcome_email": 0,
		})
		user.append("roles", {"role": "Accountant"})
		user.append("roles", {"role": "LMS Student"})

		enforce_accountant_lockdown(user)

		remaining = {r.role for r in user.roles}
		self.assertIn("Accountant", remaining)
		self.assertNotIn("LMS Student", remaining, "Non-Accountant roles should be stripped")
		self.assertEqual(user.default_workspace, "Finance")
		self.assertEqual(user.default_app, "")

	def test_hook_skips_non_accountant_users(self):
		from quality_asia_lms.overrides.accountant_lockdown import enforce_accountant_lockdown

		user = frappe.get_doc({
			"doctype": "User",
			"email": "__test_student_hook@example.com",
			"first_name": "Test",
			"user_type": "System User",
			"send_welcome_email": 0,
		})
		user.append("roles", {"role": "LMS Student"})

		enforce_accountant_lockdown(user)

		remaining = {r.role for r in user.roles}
		self.assertIn("LMS Student", remaining, "Non-Accountant user should not be modified")


class TestOperationsPerms(unittest.TestCase):
	"""Verify the Operations role grants."""

	def test_operations_can_readwrite_lms_course(self):
		perms = _get_active_perms("LMS Course")
		row = _role_perm(perms, "Operations")
		if row is None:
			self.skipTest("Operations role not yet seeded")
		self.assertTrue(row.read, "Operations lost read on LMS Course")
		self.assertTrue(row.write, "Operations lost write on LMS Course")
		self.assertTrue(row.create, "Operations lost create on LMS Course")

	def test_operations_readonly_on_lms_payment(self):
		perms = _get_active_perms("LMS Payment")
		row = _role_perm(perms, "Operations")
		if row is None:
			self.skipTest("Operations role not yet seeded")
		self.assertTrue(row.read, "Operations lost read on LMS Payment")
		self.assertFalse(row.write, "Operations should NOT have write on LMS Payment")
