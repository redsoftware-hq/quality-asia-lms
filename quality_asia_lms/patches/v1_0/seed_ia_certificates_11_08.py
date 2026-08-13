"""Seed the 11-08 batch of 611 Internal Auditor certificates.

The source spreadsheet holds personal data and is NOT in this repo — it must be
placed at sites/<site>/private/files/ before the deploy that runs this patch.

IMPORTANT: if the file is absent this patch no-ops, and Frappe records it in
Patch Log as executed regardless (patch_handler.py calls update_patch_log right
after execute() returns, and only an exception prevents that). It will then
never re-run on its own. The no-op is still required — raising would break
`bench migrate` on every environment that legitimately lacks the file.

So a missed file placement is recoverable but not automatic:

    bench --site <site> execute quality_asia_lms.setup.seed_certificates.run

That fallback is safe because the seeder is idempotent and its numbering is
pinned, so a manual run produces exactly the assignment this patch would have.
The Error Log entry below is what makes a burned run visible instead of silent.
"""

import os

import frappe

from quality_asia_lms.setup import seed_certificates


def execute():
	path = seed_certificates._default_path()
	if not os.path.exists(path):
		frappe.log_error(
			message=(
				f"Expected the certificate spreadsheet at {path}, but it was not there.\n"
				f"This patch is now recorded as executed and will NOT re-run.\n"
				f"Place the file and run:\n"
				f"  bench --site {frappe.local.site} execute "
				f"quality_asia_lms.setup.seed_certificates.run"
			),
			title="IA cert seed 11-08: data file missing, patch consumed",
		)
		return

	seed_certificates.run(path)
