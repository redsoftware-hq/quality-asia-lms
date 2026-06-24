"""Add a unique index on LMS Payment.invoice_number to prevent duplicate
invoice numbers from concurrent payments (code-review finding #2).

The index is conditional — NULL values are allowed (most rows won't have
an invoice_number yet), but two rows with the same non-NULL value are
blocked at the DB level.
"""

import frappe


def execute():
	# MariaDB: a regular UNIQUE index allows multiple NULLs by default.
	# The column is a Custom Field (Data), so it's already nullable.
	if not frappe.db.has_index("tabLMS Payment", "uniq_invoice_number"):
		frappe.db.sql(
			"""CREATE UNIQUE INDEX `uniq_invoice_number`
			ON `tabLMS Payment` (`invoice_number`)"""
		)
		frappe.db.commit()
