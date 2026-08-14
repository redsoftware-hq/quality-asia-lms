"""Seed the 12-08 Nelito batch of 13 ITSMS certificates.

Runs after seed_ia_certificates_11_08 in patches.txt, in the same
`bench migrate`. Each batch stores its own block start and allocates above the
site's current highest IAC number, so the two blocks never overlap regardless of
which one runs first.

Also creates the ITSMS course (unpublished, no content) before seeding — see
ITSMS_COURSE in setup/seed_certificates.py for why its title is the dangling
phrase "ITSMS Awareness and".

All logic lives in seed_certificates.run_from_patch so this patch and the 11-08
one cannot drift apart; see that function for the file-missing behaviour.
"""

from quality_asia_lms.setup import seed_certificates

BATCH = "itsms"


def execute():
	seed_certificates.run_from_patch(BATCH)
