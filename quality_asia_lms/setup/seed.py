"""One-time seed of Quality Asia customizations onto a fresh deployment.

Carries what NO installed app recreates on its own:
  - Branding   (Website Settings + LMS Settings runtime values)  -> force-set
  - RBAC       (admin's manual Custom DocPerm changes + Property Setters)
  - Content    (the 2 published ISO courses + chapters + lessons + instructor Users)
  - Files      (logo/favicon/footer + lesson images)

Invoked once by the patch `quality_asia_lms.patches.v1_0.seed_initial_data`
(recorded in Patch Log -> never re-runs -> later admin UI edits persist).

Manual re-run / second environment:
  bench --site <site> execute quality_asia_lms.setup.seed.run

Every step is idempotent, so the manual re-run is safe too.
"""

import json
import os
import shutil
from urllib.parse import unquote

import frappe

DATA = frappe.get_app_path("quality_asia_lms", "setup", "data")
FILES = frappe.get_app_path("quality_asia_lms", "setup", "files")


def _load(name):
	path = os.path.join(DATA, name)
	if not os.path.exists(path):
		return None
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def _log(msg):
	print(f"[qa-seed] {msg}")


# --------------------------------------------------------------------------- files
def _copy_files(manifest):
	"""Copy bundled files to the site and ensure a File record exists. Returns (copied, created)."""
	copied = created = 0
	for f in manifest:
		url = f["file_url"]
		folder = "private" if f.get("is_private") else "public"
		dest = frappe.get_site_path(folder, "files", unquote(url.split("/files/")[-1]))
		# Physical file is authoritative — /files/<x> renders from disk regardless of
		# whether a File record exists. This must succeed.
		if not os.path.exists(dest):
			os.makedirs(os.path.dirname(dest), exist_ok=True)
			src = os.path.join(FILES, f["stored_as"])
			if os.path.exists(src):
				shutil.copy(src, dest)
				copied += 1
		# File record is secondary (Files UI / attachment tracking) — best-effort,
		# never abort the deploy over it.
		if not frappe.db.exists("File", {"file_url": url}):
			try:
				frappe.get_doc({
					"doctype": "File",
					"file_url": url,
					"file_name": f.get("file_name"),
					"is_private": f.get("is_private") or 0,
				}).insert(ignore_permissions=True)
				created += 1
			except Exception:
				frappe.log_error(title=f"qa-seed: File record skipped for {url}")
	return copied, created


def seed_files():
	manifest = _load("files.json") or []
	copied, created = _copy_files(manifest)
	_log(f"files: {len(manifest)} referenced, {copied} copied to disk, {created} File records created")


# ------------------------------------------------------------------------- branding
def seed_branding():
	b = _load("branding.json") or {}
	for single, vals in (("Website Settings", b.get("website_settings")),
						("LMS Settings", b.get("lms_settings"))):
		for k, v in (vals or {}).items():
			frappe.db.set_value(single, single, k, v)
	_log("branding: Website Settings + LMS Settings force-set")


# ----------------------------------------------------------------------------- rbac
def seed_rbac():
	from frappe.permissions import setup_custom_perms

	d = _load("rbac.json") or {}
	touched = set()
	for p in d.get("custom_docperm", []):
		# Clone standard DocPerm rows into Custom DocPerm first so they are not
		# silently discarded once we insert our custom row (see QA-38 hotfix).
		setup_custom_perms(p["parent"])  # no-op when Custom DocPerm already exists

		flt = {"parent": p["parent"], "role": p["role"], "permlevel": p["permlevel"]}
		name = frappe.db.exists("Custom DocPerm", flt)
		doc = frappe.get_doc("Custom DocPerm", name) if name else frappe.new_doc("Custom DocPerm")
		doc.update(p)
		doc.parenttype = "DocType"
		doc.parentfield = "permissions"
		doc.flags.ignore_permissions = True
		doc.save()
		touched.add(p["parent"])
	for ps in d.get("property_setter", []):
		flt = {"doc_type": ps["doc_type"], "property": ps["property"]}
		if ps.get("field_name"):
			flt["field_name"] = ps["field_name"]
		name = frappe.db.exists("Property Setter", flt)
		doc = frappe.get_doc("Property Setter", name) if name else frappe.new_doc("Property Setter")
		doc.update(ps)
		doc.flags.ignore_permissions = True
		doc.save()
		touched.add(ps["doc_type"])
	for dt in touched:
		frappe.clear_cache(doctype=dt)
	_log(f"rbac: {len(d.get('custom_docperm', []))} perms, "
		f"{len(d.get('property_setter', []))} property setters applied")


# ---------------------------------------------------------------------------- users
def seed_users():
	users = _load("users.json") or []
	for u in users:
		u = dict(u)
		roles = u.pop("roles", [])
		email = u["email"]
		if frappe.db.exists("User", email):
			doc = frappe.get_doc("User", email)
			doc.update({k: v for k, v in u.items() if k != "email"})
		else:
			doc = frappe.new_doc("User")
			doc.update(u)
			doc.flags.no_welcome_mail = True
		have = {r.role for r in doc.roles}
		for r in roles:
			if r not in have and frappe.db.exists("Role", r):
				doc.append("roles", {"role": r})
		doc.flags.ignore_permissions = True
		doc.save()
	_log(f"users: {len(users)} instructor user(s) ensured")


# -------------------------------------------------------------------------- courses
def _upsert(dt, data):
	data = dict(data)
	data.pop("doctype", None)
	name = data.get("name")
	if name and frappe.db.exists(dt, name):
		doc = frappe.get_doc(dt, name)
		doc.update(data)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_links = True
		doc.flags.ignore_mandatory = True
		doc.save()
	else:
		doc = frappe.get_doc({**data, "doctype": dt})
		doc.flags.ignore_permissions = True
		doc.flags.ignore_links = True
		doc.flags.ignore_mandatory = True
		doc.insert(set_name=name)
	return doc


def seed_quizzes():
	"""Questions then quizzes — MUST run before lessons, because
	Course Lesson.on_update validates that embedded quizzes already exist."""
	questions = _load("questions.json") or []
	quizzes = _load("quizzes.json") or []
	for q in questions:
		_upsert("LMS Question", q)
	for quiz in quizzes:
		_upsert("LMS Quiz", quiz)
	_log(f"quizzes: {len(questions)} question(s), {len(quizzes)} quiz(zes) upserted")


def seed_courses():
	data = _load("courses.json") or []
	# dependency order: lessons -> chapters -> course (links resolve, ignore_links covers cycles)
	for c in data:
		for ch in c["chapters"]:
			for lesson in ch["lessons"]:
				_upsert("Course Lesson", lesson)
	for c in data:
		for ch in c["chapters"]:
			_upsert("Course Chapter", ch["chapter"])
	for c in data:
		_upsert("LMS Course", c["course"])
	_log(f"courses: {len(data)} course(s) upserted (update-to-match snapshot)")


# ----------------------------------------------------------- ISO auditor courses
def seed_iso_auditor_courses():
	"""The 10 free/paid ISO Internal Auditor courses generated from the client's
	content sheet. Owns these course slugs end-to-end and overrides whatever the
	earlier seed_courses() produced for the same slugs (e.g. ISO 27701 / 42001).

	Quiz questions are delivered by the client incrementally; quizzes with no
	questions yet are seeded as empty stubs (the course still publishes) and are
	filled in place on a later re-run. Existing LMS Quiz/Question docs are never
	deleted, so nothing is lost while questions are pending.
	"""
	courses = _load("courses_iso_auditor.json") or []
	if not courses:
		_log("iso-auditor: no course data found, skipping")
		return

	_copy_files(_load("files_iso_auditor.json") or [])

	# reconcile structure: drop only the chapters/lessons of OUR courses that are
	# no longer part of the new definition (keeps the old 2-chapter layout from
	# lingering). Quizzes and questions are intentionally left untouched.
	new_chapters, new_lessons = set(), set()
	for c in courses:
		for ch in c["chapters"]:
			new_chapters.add(ch["chapter"]["name"])
			for lesson in ch["lessons"]:
				new_lessons.add(lesson["name"])
	for c in courses:
		slug = c["course"]["name"]
		for ln in frappe.get_all("Course Lesson", filters={"course": slug}, pluck="name"):
			if ln not in new_lessons:
				frappe.delete_doc("Course Lesson", ln, force=True, ignore_permissions=True)
		for cn in frappe.get_all("Course Chapter", filters={"course": slug}, pluck="name"):
			if cn not in new_chapters:
				frappe.delete_doc("Course Chapter", cn, force=True, ignore_permissions=True)

	# questions before quizzes (quiz rows reference question names),
	# quizzes before lessons (Course Lesson.on_update validates embedded quizzes).
	for q in (_load("questions_iso_auditor.json") or []):
		_upsert("LMS Question", q)
	quizzes = _load("quizzes_iso_auditor.json") or []
	for quiz in quizzes:
		_upsert("LMS Quiz", quiz)

	# lessons -> chapters -> course
	for c in courses:
		for ch in c["chapters"]:
			for lesson in ch["lessons"]:
				_upsert("Course Lesson", lesson)
	for c in courses:
		for ch in c["chapters"]:
			_upsert("Course Chapter", ch["chapter"])
	for c in courses:
		_upsert("LMS Course", c["course"])

	pending = [q["name"] for q in quizzes if not q.get("questions")]
	_log(f"iso-auditor: {len(courses)} course(s) upserted")
	if pending:
		_log(f"iso-auditor: {len(pending)} quiz(zes) still awaiting client questions: {pending}")


# ------------------------------------------------------------------------------ run
def run(commit=True):
	_log("seeding Quality Asia customizations …")
	seed_files()
	seed_branding()
	seed_rbac()
	seed_users()
	seed_quizzes()  # before courses: lessons validate embedded quizzes exist
	seed_courses()
	if commit:
		frappe.db.commit()
	_log("done.")


def run_iso_auditor_courses(commit=True):
	"""Seed just the 10 ISO Internal Auditor courses. Invoked by the
	`seed_iso_auditor_courses` patch, and runnable manually:

	  bench --site <site> execute quality_asia_lms.setup.seed.run_iso_auditor_courses
	"""
	_log("seeding ISO Internal Auditor courses …")
	seed_users()  # ensure the instructor User exists before linking courses
	seed_iso_auditor_courses()
	if commit:
		frappe.db.commit()
	_log("done.")
