"""QA-38 hotfix: restore standard DocPerm rows wiped by Custom DocPerm inserts.

``seed_roles_and_accountant`` (QA-33/34) inserted Custom DocPerm rows for
Operations/Accountant without first cloning the doctype's standard permission
rows.  Frappe's permission resolver discards ALL standard ``DocPerm`` entries
once ANY ``Custom DocPerm`` exists for a doctype, so roles like ``LMS Student``
silently lost their create/read/write access.

This patch copies any **missing** standard rows back into ``Custom DocPerm``
(keyed by parent + role + permlevel + if_owner), without touching rows that
already exist — so the Operations/Accountant grants are preserved.

Idempotent — safe to re-run.
"""

import frappe

# Doctypes affected by seed_roles_and_accountant's direct Custom DocPerm inserts.
AFFECTED = [
	"Address",
	"LMS Payment",
	"LMS Course",
	"LMS Quiz",
	"LMS Question",
	"LMS Certificate",
	"LMS Enrollment",
]

# Fields to skip when copying a DocPerm row into Custom DocPerm.
_SKIP = frozenset(("name", "creation", "modified", "owner", "modified_by", "idx", "doctype"))


def execute():
	restored = 0

	for dt in AFFECTED:
		if not frappe.db.exists("Custom DocPerm", {"parent": dt}):
			continue  # no Custom DocPerm → standard rows are still active, nothing to fix

		standard_rows = frappe.get_all("DocPerm", filters={"parent": dt}, fields=["*"])
		for std in standard_rows:
			already = frappe.db.exists(
				"Custom DocPerm",
				{
					"parent": dt,
					"role": std.role,
					"permlevel": std.permlevel,
					"if_owner": std.if_owner,
				},
			)
			if already:
				continue

			cp = frappe.new_doc("Custom DocPerm")
			cp.update({k: v for k, v in std.items() if k not in _SKIP})
			cp.parenttype = "DocType"
			cp.parentfield = "permissions"
			cp.insert(ignore_permissions=True)
			restored += 1

		frappe.clear_cache(doctype=dt)

	if restored:
		frappe.db.commit()

	frappe.logger("qa_lms").info(
		f"restore_standard_docperms: restored {restored} missing Custom DocPerm rows "
		f"across {len(AFFECTED)} doctypes"
	)
