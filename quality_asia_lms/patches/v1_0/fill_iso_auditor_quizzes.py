"""Fill the 9 empty ISO Internal Auditor exam quiz stubs with questions extracted
from the Google Forms response sheets, and add a standardised Training Feedback
quiz + chapter to each of those 9 courses.

Questions for each course were extracted offline by
``quality_asia_lms/setup/tools/extract_quiz_from_forms.py`` and committed to
``setup/data/questions_iso_auditor.json`` / ``quizzes_iso_auditor.json``.

This patch re-runs ``seed_iso_auditor_courses`` under a new name so it fires
exactly once on sites that already have the previous ``seed_iso_auditor_courses``
patch recorded in Patch Log (which only seeded the empty stubs).
"""

import frappe

from quality_asia_lms.setup import seed


def execute():
	try:
		seed.run_iso_auditor_courses(commit=False)  # migrate wraps this in its own transaction
	except Exception:
		frappe.log_error(title="quality_asia_lms fill_iso_auditor_quizzes failed")
		raise
