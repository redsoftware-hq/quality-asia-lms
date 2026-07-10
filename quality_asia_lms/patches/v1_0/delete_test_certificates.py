"""Delete 3 hash-named test certificates from production.

These were created during manual testing before QA-30 introduced IAC-XXXXX
autoname. Idempotent — safe to re-run.
"""

import frappe

TEST_CERT_IDS = ["0jknhmauir", "ev65mbd4ai", "fd4052f7u0"]


def execute():
	for cert_id in TEST_CERT_IDS:
		if not frappe.db.exists("LMS Certificate", cert_id):
			continue
		for enr in frappe.db.get_all("LMS Enrollment", filters={"certificate": cert_id}, pluck="name"):
			frappe.db.set_value("LMS Enrollment", enr, "certificate", None, update_modified=False)
		frappe.delete_doc("LMS Certificate", cert_id, ignore_permissions=True, force=True)

	frappe.db.commit()
