"""Re-run ISO 26000 consolidation (retries after deadlock on first deploy).

The original consolidate_iso_26000 patch was logged as complete in the Patch
Log despite a deadlock aborting the actual work. Frappe will never re-run a
logged patch, so this wrapper re-invokes the same idempotent execute().
"""

from quality_asia_lms.patches.v1_0 import consolidate_iso_26000


def execute():
	consolidate_iso_26000.execute()
