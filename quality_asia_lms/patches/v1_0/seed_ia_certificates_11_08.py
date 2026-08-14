"""Seed the 11-08 batch of 611 Internal Auditor certificates.

The source spreadsheet holds personal data and is NOT in this repo — it must be
uploaded as a private file (Desk -> File Manager) before the deploy that runs
this patch.

All logic lives in seed_certificates.run_from_patch so this patch and the ITSMS
one cannot drift apart; see that function for the file-missing behaviour and why
it exists.
"""

from quality_asia_lms.setup import seed_certificates

BATCH = "11_08"


def execute():
	seed_certificates.run_from_patch(BATCH)
