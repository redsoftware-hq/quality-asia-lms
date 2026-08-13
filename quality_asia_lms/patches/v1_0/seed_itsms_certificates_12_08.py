"""Seed the 12-08 Nelito batch of 13 ITSMS certificates.

Runs immediately after seed_ia_certificates_11_08 in patches.txt, in the same
`bench migrate`. That order matters: the 11-08 batch claims the top of its
number block on its first insert, so this batch's _scan_max_iac sees that
ceiling and allocates cleanly above it. Each batch stores its own block start
under its own key, so neither can read the other's allocation.

Also creates the ITSMS course (unpublished, no content) before seeding — see
ITSMS_COURSE in setup/seed_certificates.py for why its title is the dangling
phrase "ITSMS Awareness and".

Same caveat as the 11-08 patch: if the spreadsheet is absent this no-ops, and
Frappe records it as executed regardless, so it will not retry on its own. It
logs to Error Log in that case and the seeder stays runnable by hand:

    bench --site <site> execute quality_asia_lms.setup.seed_certificates.run \\
        --kwargs "{'batch': 'itsms'}"
"""

import os

import frappe

from quality_asia_lms.setup import seed_certificates

BATCH = "itsms"


def execute():
	batch = seed_certificates.BATCHES[BATCH]
	path = seed_certificates._default_path(batch)
	if not os.path.exists(path):
		frappe.log_error(
			message=(
				f"Expected the ITSMS spreadsheet at {path}, but it was not there.\n"
				f"This patch is now recorded as executed and will NOT re-run.\n"
				f"Place the file and run:\n"
				f"  bench --site {frappe.local.site} execute "
				f"quality_asia_lms.setup.seed_certificates.run --kwargs \"{{'batch': '{BATCH}'}}\""
			),
			title="ITSMS cert seed 12-08: data file missing, patch consumed",
		)
		return

	seed_certificates.run(path, batch=BATCH)
