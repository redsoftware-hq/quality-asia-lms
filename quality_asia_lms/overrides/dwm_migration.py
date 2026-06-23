import gzip
import os
import re

import frappe

TEMPLATE = "QA Certificate"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TABLE = "tabInternal Auditor Training Certificate"
_NEEDED = frozenset([
	"name", "candidate_name", "email_id", "contact_number",
	"training_program_name", "date_of_issue", "training_dates",
	"creation", "modified",
])


def _default_dump_path():
	return frappe.get_site_path("private", "files", "dwm_certificates.sql.gz")


# ── SQL dump parser ──────────────────────────────────────────────────────────


def _split_row_groups(insert_line):
	"""Extract individual row contents from a VALUES (...),(...)... INSERT line."""
	idx = insert_line.upper().find("VALUES ")
	if idx == -1:
		return []
	tail = insert_line[idx + 7 :].rstrip(";\n ")
	groups = []
	depth = 0
	in_str = False
	start = None
	i = 0
	while i < len(tail):
		c = tail[i]
		if in_str:
			if c == "\\":
				i += 2
				continue
			elif c == "'":
				in_str = False
		else:
			if c == "'":
				in_str = True
			elif c == "(":
				if depth == 0:
					start = i + 1
				depth += 1
			elif c == ")":
				depth -= 1
				if depth == 0 and start is not None:
					groups.append(tail[start:i])
					start = None
		i += 1
	return groups


def _parse_sql_values(s):
	"""Parse comma-separated SQL values from inside a row group string."""
	_ESC = {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}
	values = []
	i = 0
	n = len(s)
	while i < n:
		while i < n and s[i] in (" ", "\t"):
			i += 1
		if i >= n:
			break
		if s[i] == "'":
			i += 1
			buf = []
			while i < n:
				c = s[i]
				if c == "\\":
					i += 1
					if i < n:
						buf.append(_ESC.get(s[i], s[i]))
						i += 1
				elif c == "'":
					i += 1
					break
				else:
					buf.append(c)
					i += 1
			values.append("".join(buf))
		elif s[i : i + 4] == "NULL":
			values.append(None)
			i += 4
		else:
			j = i
			while i < n and s[i] != ",":
				i += 1
			values.append(s[j:i].strip() or None)
		while i < n and s[i] in (" ", "\t"):
			i += 1
		if i < n and s[i] == ",":
			i += 1
	return values


def _iter_rows(dump_path):
	"""Stream certificate record dicts from a Frappe mysqldump .sql.gz file."""
	columns = []
	in_create = False

	with gzip.open(dump_path, "rt", encoding="utf-8", errors="replace") as f:
		for line in f:
			line = line.rstrip("\n")

			if f"CREATE TABLE `{_TABLE}`" in line:
				in_create = True
				columns = []
				continue

			if in_create:
				stripped = line.strip()
				if stripped.startswith("`"):
					m = re.match(r"`([^`]+)`", stripped)
					if m:
						columns.append(m.group(1))
				if stripped.startswith(")"):
					in_create = False
				continue

			if columns and f"INSERT INTO `{_TABLE}`" in line:
				for group in _split_row_groups(line):
					vals = _parse_sql_values(group)
					if len(vals) != len(columns):
						continue
					row = dict(zip(columns, vals))
					yield {k: row.get(k) for k in _NEEDED}


# ── Course resolution ────────────────────────────────────────────────────────

_course_titles: dict | None = None  # normalized title -> course name


def _build_course_cache():
	global _course_titles
	_course_titles = {}
	for name, title in frappe.get_all("LMS Course", fields=["name", "title"], as_list=True):
		key = (title or "").strip().lower()
		if key:
			_course_titles[key] = name


_YEAR_SUFFIX_RE = re.compile(r":\d{4}$")


def _normalize(s):
	"""Strip trailing ':YYYY' and whitespace, lowercase."""
	return _YEAR_SUFFIX_RE.sub("", (s or "").strip()).strip().lower()


def _resolve_course(program):
	if _course_titles is None:
		_build_course_cache()
	key = (program or "").strip().lower()
	stripped = _normalize(program)
	# 1. exact match, 2. year-stripped exact match, 3. year-stripped substring of course title
	return (
		_course_titles.get(key)
		or _course_titles.get(stripped)
		or next((name for title, name in _course_titles.items() if stripped in title), None)
	)


# ── User helpers ─────────────────────────────────────────────────────────────

_user_cache: set = set()


def _clean_mobile(raw):
	if not raw:
		return None
	digits = re.sub(r"[^\d+]", "", raw.strip())
	digits = re.sub(r"^\++", "+", digits)
	pure = digits.lstrip("+")
	return digits if 7 <= len(pure) <= 15 else None


def _is_valid_email(addr):
	try:
		from frappe.utils import validate_email_address

		validate_email_address(addr, throw=True)
		return True
	except Exception:
		return False


def _user(name, email, mobile, placeholder_log):
	email = (email or "").strip().lower()
	clean_mobile = _clean_mobile(mobile)
	if not EMAIL_RE.match(email) or not _is_valid_email(email):
		suffix = re.sub(r"\D", "", mobile or "")[-4:] or "0000"
		local = frappe.scrub(name).replace("_", ".")
		local = re.sub(r"\.{2,}", ".", local).strip(".")
		email = f"{local or 'candidate'}.{suffix}@placeholder.qualityasia.in"
		placeholder_log.append((name, mobile, email))
	if email not in _user_cache:
		if not frappe.db.exists("User", email):
			parts = (name or "").strip().split(" ", 1)
			if clean_mobile and frappe.db.exists("User", {"mobile_no": clean_mobile}):
				clean_mobile = None
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": parts[0] or "Candidate",
					"last_name": parts[1] if len(parts) > 1 else "",
					"mobile_no": clean_mobile,
					"enabled": 1,
					"user_type": "Website User",
					"send_welcome_email": 0,
					"is_migrated": 1,
					"roles": [{"role": "LMS Student"}],
				}
			).insert(ignore_permissions=True)
		_user_cache.add(email)
	return email


# ── Entry points ─────────────────────────────────────────────────────────────


def reconcile(path=None):
	"""Preview how each source training program resolves against the current site.

	Read-only — run this before run() to confirm course title matching.
	Programs shown as UNMAPPED will be skipped until a course with that title exists.
	"""
	path = path or _default_dump_path()
	rows = list(_iter_rows(path))
	programs: dict[str, int] = {}
	for row in rows:
		p = row["training_program_name"]
		programs[p] = programs.get(p, 0) + 1
	existing = sum(1 for r in rows if frappe.db.exists("LMS Certificate", r["name"]))
	print(f"{path}: {len(rows)} rows, {existing} already migrated\n")
	print(f"{'rows':>6}  {'program':<50} resolution")
	for program, count in sorted(programs.items(), key=lambda kv: -kv[1]):
		name = _resolve_course(program)
		status = f"-> {name}" if name else "UNMAPPED (rows will be skipped)"
		print(f"{count:>6}  {program:<50} {status}")


def run(path=None, template=None):
	path = path or _default_dump_path()
	template = template or TEMPLATE
	placeholder_log: list = []

	# reset module-level caches so each run picks up current DB state
	global _course_titles, _user_cache
	_course_titles = None
	_user_cache = set()

	# bypass user-creation throttle, queue size check, and import-unfriendly validations
	frappe.flags.in_import = True
	frappe.flags.in_install = True  # makes User.on_update run create_contact synchronously

	rows = list(_iter_rows(path))

	created = skipped = failed = 0
	unmapped_rows: list = []
	for row in rows:
		old_id = row["name"]
		if frappe.db.exists("LMS Certificate", old_id):
			skipped += 1
			continue
		course = _resolve_course(row["training_program_name"])
		if not course:
			unmapped_rows.append(row)
			continue
		try:
			member = _user(
				row["candidate_name"], row.get("email_id"), row.get("contact_number"), placeholder_log
			)

			enrollment_name = frappe.db.get_value("LMS Enrollment", {"member": member, "course": course})
			if not enrollment_name:
				enrollment = frappe.get_doc(
					{
						"doctype": "LMS Enrollment",
						"member": member,
						"course": course,
						"progress": 100,
					}
				)
				enrollment.flags.ignore_permissions = True
				enrollment.flags.ignore_mandatory = True
				enrollment.insert()
				enrollment_name = enrollment.name

			cert = frappe.get_doc(
				{
					"doctype": "LMS Certificate",
					"member": member,
					"course": course,
					"issue_date": row["date_of_issue"],
					"template": template,
					"published": 1,
					"training_dates": row.get("training_dates"),
					"candidate_name_as_printed": row["candidate_name"],
					"is_migrated": 1,
				}
			)
			cert.flags.ignore_permissions = True
			cert.flags.ignore_validate = (
				True  # bypass duplicate-cert-per-course check; historical data may have multiples
			)
			cert.insert(set_name=old_id)

			frappe.db.set_value(
				"LMS Certificate",
				old_id,
				{"creation": row["creation"], "modified": row["modified"]},
				update_modified=False,
			)
			frappe.db.set_value(
				"LMS Enrollment", enrollment_name, "certificate", old_id, update_modified=False
			)

			created += 1
			if created % 500 == 0:
				frappe.db.commit()
				print(created, "done")
		except Exception:
			frappe.log_error(title=f"Cert migration failed: {old_id}")
			failed += 1

	import csv as _csv
	import io

	frappe.db.commit()

	if placeholder_log:
		buf = io.StringIO()
		_csv.writer(buf).writerows(
			[("candidate_name", "mobile", "placeholder_email"), *placeholder_log]
		)
		_save_private_file("dwm_placeholder_users.csv", buf.getvalue())

	if unmapped_rows:
		buf = io.StringIO()
		writer = _csv.DictWriter(buf, fieldnames=sorted(_NEEDED), delimiter="\t")
		writer.writeheader()
		writer.writerows(unmapped_rows)
		_save_private_file("dwm_unmapped_rows.tsv", buf.getvalue())

	summary = (
		f"created={created} skipped={skipped} unmapped={len(unmapped_rows)} "
		f"failed={failed} placeholders={len(placeholder_log)}"
	)
	print(summary)
	return summary


def validate():
	"""Return a summary string of current certificate/course/user counts."""
	certs = frappe.db.count("LMS Certificate")
	courses = frappe.db.count("LMS Course")
	students = frappe.db.count("User", {"user_type": "Website User"})
	orphans = frappe.db.sql("""
		SELECT c.name FROM `tabLMS Certificate` c
		LEFT JOIN `tabLMS Enrollment` e
		  ON e.member = c.member AND e.course = c.course
		WHERE e.name IS NULL AND c.course IS NOT NULL
	""")
	unpublished = frappe.db.count("LMS Certificate", {"published": 0})
	lines = [
		f"certificates={certs} courses={courses} website_users={students} "
		f"orphan_certs={len(orphans)} unpublished={unpublished}"
	]
	if orphans:
		lines.append(f"ORPHANS: {[o[0] for o in orphans][:20]}")
	result = "\n".join(lines)
	print(result)
	return result


def _save_private_file(filename, content):
	"""Write content as a private File record visible in Frappe Desk → File Manager."""
	from frappe.utils.file_manager import save_file

	if isinstance(content, str):
		content = content.encode("utf-8")
	# remove stale record so save_file doesn't collide on duplicate name
	existing = frappe.db.get_value("File", {"file_name": filename, "is_private": 1})
	if existing:
		frappe.delete_doc("File", existing, ignore_permissions=True, force=True)
	save_file(filename, content, dt="", dn="", is_private=1)


def migrate_if_dump_present():
	"""Called by after_migrate hook — no-op when dump file is absent.

	Runs the migration and saves results as private File records visible in
	Frappe Desk → File Manager — no console access needed.
	"""
	from datetime import datetime

	from quality_asia_lms.overrides.migrated_users import enable_real_email_users

	path = _default_dump_path()
	if not os.path.exists(path):
		return

	run_summary = run(path)
	validate_summary = validate()

	enable_real_email_users()

	log = f"--- {datetime.utcnow().isoformat()} UTC ---\nrun:      {run_summary}\nvalidate: {validate_summary}\n"
	_save_private_file("dwm_migration_log.txt", log)
	frappe.db.commit()
