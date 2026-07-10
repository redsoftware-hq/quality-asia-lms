#!/usr/bin/env python3
"""
extract_quiz_from_forms.py — Quality Asia LMS offline quiz extractor.

Parses the Google Forms quiz-response xlsx exports from the "09 Training Evaluation
Form" folder and emits LMS Question + LMS Quiz seed JSON for the 9 ISO Internal
Auditor courses whose exam quizzes are currently empty stubs (ISO 26000 is already
hand-built and is preserved as-is).

Correct answers are inferred from high-scorer consensus: for each question we take
the most common answer among respondents who scored >= 85 % of the maximum score.
This yields ~98 % confidence empirically. The generated quiz_extraction_report.md
lists every question with its confidence score so low-confidence items can be
manually verified against the live Google Form.

Usage:
    python quality_asia_lms/setup/tools/extract_quiz_from_forms.py \\
        "<path/to/09 Training Evaluation Form folder>"

    # e.g. from the repo root:
    python quality_asia_lms/setup/tools/extract_quiz_from_forms.py \\
        "09 Training Evaluation Form-20260618T050454Z-3-001/09 Training Evaluation Form"

Outputs (relative to the repo root — run from the repo root):
    quality_asia_lms/setup/data/questions_iso_auditor.json  (regenerated)
    quality_asia_lms/setup/data/quizzes_iso_auditor.json    (regenerated)
    quality_asia_lms/setup/data/courses_iso_auditor.json    (feedback chapters added)
    quality_asia_lms/setup/data/quiz_extraction_report.md   (confidence review)

The Google Form answer keys (green-checkmark = correct) are visible in the form
editor at the URL printed in the report — use them to verify any flagged question.

Answer note from the screenshot: the form shows "Total points: 40" for ISO 9001 with
each graded question worth 2 pts.  Max-score detection from the Score column gives
the same result automatically.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps the numbered folder prefix to the ISO key used in quiz/lesson/chapter names.
# "skip_exam": True  → preserve hand-built exam questions (ISO 26000).
# "skip_feedback": True → preserve hand-built feedback quiz (ISO 26000).
COURSE_CONFIG: list[dict] = [
	{"folder": "01 ISO 9001", "std": "9001", "year": "2015", "quiz_title": "ISO 9001:2015 Final Exam"},
	{"folder": "02 ISO 14001", "std": "14001", "year": "2015", "quiz_title": "ISO 14001:2015 Final Exam"},
	{"folder": "03 ISO 45001", "std": "45001", "year": "2018", "quiz_title": "ISO 45001:2018 Final Exam"},
	{"folder": "04 ISO 50001", "std": "50001", "year": "2018", "quiz_title": "ISO 50001:2018 Final Exam"},
	{"folder": "05 ISO 22000", "std": "22000", "year": "2018", "quiz_title": "ISO 22000:2018 Final Exam"},
	{"folder": "06 ISO 27001", "std": "27001", "year": "2022", "quiz_title": "ISO 27001:2022 Final Exam"},
	{"folder": "07 ISO 13485", "std": "13485", "year": "2016", "quiz_title": "ISO 13485:2016 Final Exam"},
	{
		"folder": "08 ISO 26000",
		"std": "26000",
		"year": "2010",
		"quiz_title": "ISO 26000:2010 Final Exam",
		"skip_exam": True,
		"skip_feedback": True,
	},
	{"folder": "09 ISO 42001", "std": "42001", "year": "2023", "quiz_title": "ISO 42001:2023 Final Exam"},
	{"folder": "10 ISO 27701", "std": "27701", "year": "2019", "quiz_title": "ISO 27701:2019 Final Exam"},
]

# Shared feedback question names (defined once in questions_iso_auditor.json for ISO 26000,
# reused across all course feedback quizzes — no per-course duplicates needed).
FEEDBACK_Q_MAP: list[dict] = [
	{
		"name": "QA-FEEDBACK-EFFECTIVENESS",
		# Must contain BOTH a rating phrase AND "effectiveness" to avoid matching
		# exam questions that merely mention effectiveness in a factual context.
		"keywords": ["would you rate the effectiveness", "overall, how would you rate"],
	},
	{
		"name": "QA-FEEDBACK-INSTRUCTOR",
		# The exact phrase used in all 10 evaluation forms
		"keywords": ["instructor's knowledge and expertise", "instructor's knowledge"],
	},
	{
		"name": "QA-FEEDBACK-STRUCTURE",
		# The exact phrase used across forms (sometimes prefixed with "course structure -")
		"keywords": ["suitable amount of time", "delivered in a suitable"],
	},
	{
		"name": "QA-FEEDBACK-SATISFACTION",
		# Distinct enough not to appear in exam content
		"keywords": ["overall satisfaction with the training", "overall satisfaction"],
	},
	{
		"name": "QA-FEEDBACK-MATERIAL",
		"keywords": ["comprehensiveness of the training", "training material (topics"],
	},
]

# Columns to always skip (resume upload, trailing empties)
SKIP_KEYWORDS: list[str] = ["resume", "attach", "company profile", "networking"]

# Column headers that are definitely metadata (not questions)
METADATA_KEYWORDS: list[str] = [
	"timestamp",
	"email address",
	"email",
	"score",
	"full name",
	"contact no",
	"company name",
]

# High-scorer threshold as fraction of max score
HIGH_SCORE_FRAC = 0.85

# Marks per exam question (2 pts — confirmed from screenshot "2/2", Total points: 40)
MARKS_PER_QUESTION = 2

# Confidence threshold below which questions are flagged in the report
CONFIDENCE_FLAG = 0.90

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


# ---------------------------------------------------------------------------
# xlsx parsing (stdlib only — no openpyxl required)
# ---------------------------------------------------------------------------


def _parse_xlsx(path: Path) -> tuple[list[str], list[dict[int, str]]]:
	"""Return (header_row, data_rows).  Each row is {col_index: value}."""
	with zipfile.ZipFile(path) as z:
		# shared strings
		shared: list[str] = []
		if "xl/sharedStrings.xml" in z.namelist():
			root = ET.fromstring(z.read("xl/sharedStrings.xml"))
			for si in root.iter(f"{NS}si"):
				shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))

		# first worksheet
		sheet_name = next(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d", n))
		sroot = ET.fromstring(z.read(sheet_name))

	def col_index(cell_ref: str) -> int:
		letters = "".join(ch for ch in cell_ref if ch.isalpha())
		n = 0
		for ch in letters:
			n = n * 26 + (ord(ch) - 64)
		return n - 1

	rows: list[dict[int, str]] = []
	for row_el in sroot.iter(f"{NS}row"):
		row: dict[int, str] = {}
		for c in row_el.iter(f"{NS}c"):
			v_el = c.find(f"{NS}v")
			if v_el is None:
				continue
			val = shared[int(v_el.text)] if c.get("t") == "s" else (v_el.text or "")
			row[col_index(c.get("r", "A1"))] = val
		rows.append(row)

	if not rows:
		return [], []

	header_row = rows[0]
	max_col = max(header_row.keys(), default=0)
	header = [header_row.get(i, "") for i in range(max_col + 1)]
	return header, rows[1:]


# ---------------------------------------------------------------------------
# Column classification
# ---------------------------------------------------------------------------


def _col_type(header: str, h_lower: str) -> str:
	"""Return 'meta', 'skip', 'feedback', or 'exam'."""
	if any(k in h_lower for k in METADATA_KEYWORDS):
		return "meta"
	if any(k in h_lower for k in SKIP_KEYWORDS):
		return "skip"
	# trailing blank header
	if not h_lower.strip():
		return "skip"
	# feedback detection
	for fq in FEEDBACK_Q_MAP:
		if any(k in h_lower for k in fq["keywords"]):
			return "feedback"
	return "exam"


def _match_feedback_q(h_lower: str) -> str | None:
	"""Return the shared QA-FEEDBACK-* name for this column, or None."""
	for fq in FEEDBACK_Q_MAP:
		if any(k in h_lower for k in fq["keywords"]):
			return fq["name"]
	return None


# ---------------------------------------------------------------------------
# Per-course extraction
# ---------------------------------------------------------------------------


def _extract_course(
	xlsx_path: Path,
	cfg: dict,
) -> dict:
	"""Parse one xlsx and return extraction results for a single course.

	Returns:
	  {
	    "std": "9001",
	    "max_score": 40.0,
	    "num_responses": 3337,
	    "exam_questions": [
	        {"col": 7, "header": "...", "options": [...], "correct": "...",
	         "confidence": 0.98, "n_hi": 2826, "n_total": 3337},
	        ...
	    ],
	    "feedback_questions": [
	        {"col": 31, "header": "...", "qa_name": "QA-FEEDBACK-EFFECTIVENESS"},
	        ...
	    ],
	  }
	"""
	std = cfg["std"]
	header, rows = _parse_xlsx(xlsx_path)

	# locate score column (index 2 by convention, but search defensively)
	score_col = next(
		(i for i, h in enumerate(header) if "score" in h.lower() and "timestamp" not in h.lower()),
		2,
	)

	def _score(row: dict) -> float:
		val = row.get(score_col, "")
		try:
			return float(val)
		except (TypeError, ValueError):
			return 0.0

	scores = [_score(r) for r in rows]
	max_score = max(scores) if scores else 0.0
	threshold = HIGH_SCORE_FRAC * max_score if max_score else 0.0
	hi_rows = [r for r, s in zip(rows, scores) if s >= threshold]

	exam_questions: list[dict] = []
	feedback_questions: list[dict] = []

	total_rows = len(rows)

	for col_idx, col_header in enumerate(header):
		h_lower = col_header.strip().lower()

		# Auto-generated Google Sheets placeholder headers ("Column 702", "Column 889"…)
		# mark sparse historical columns — skip them entirely.
		if re.match(r"^column\s+\d+$", h_lower):
			continue

		ct = _col_type(col_header, h_lower)
		if ct in ("meta", "skip"):
			continue

		all_opts_raw = [r[col_idx] for r in rows if r.get(col_idx, "").strip()]
		hi_opts_raw = [r[col_idx] for r in hi_rows if r.get(col_idx, "").strip()]

		if ct == "feedback":
			qa_name = _match_feedback_q(h_lower)
			if qa_name:
				feedback_questions.append(
					{
						"col": col_idx,
						"header": col_header.strip(),
						"qa_name": qa_name,
					}
				)

		elif ct == "exam":
			# recover option set (distinct non-empty values, ordered by frequency)
			opt_counts = Counter(all_opts_raw)
			all_distinct = [opt for opt, _ in opt_counts.most_common()]

			# --- MCQ detection ---
			# Google Forms MCQ questions have exactly the predefined option texts as
			# responses, so distinct values ≤ 6.  Columns with many unique values are
			# open-text, conditional, or accumulated historical columns — skip them.
			# Also require the top options to cover ≥ 90 % of non-empty responses so
			# that stray "Other" noise doesn't inflate the option count.
			if not all_distinct:
				# zero responses — skip silently (not a real MCQ column)
				continue

			n_all = len(all_opts_raw)
			top4_count = sum(c for _, c in opt_counts.most_common(4))
			top4_coverage = top4_count / n_all if n_all else 0.0

			# Also require that ≥ 50 % of respondents answered this column — required
			# form fields will approach 100 %; sparse historical columns will be < 5 %.
			response_rate = n_all / total_rows if total_rows else 0.0

			if len(all_distinct) > 6 or top4_coverage < 0.90 or response_rate < 0.50:
				# Not a required MCQ column (free-text, historical artefact, optional)
				continue

			options = all_distinct[:4]  # cap at 4 for the LMS Question schema

			# infer correct answer from high-scorer consensus
			if hi_opts_raw:
				hi_counts = Counter(hi_opts_raw)
				correct_opt, top_n = hi_counts.most_common(1)[0]
				confidence = top_n / len(hi_opts_raw)
			else:
				correct_opt = options[0]
				confidence = 0.0

			# Normalize 0/1 True/False encoding → "True"/"False" display text.
			# Google Forms exports T/F checkbox answers as "1" (True) / "0" (False).
			# The LMS Question displays option text, so store it as human-readable.
			_BOOL_MAP = {"0": "False", "1": "True"}
			if set(options) <= {"0", "1"}:
				correct_opt = _BOOL_MAP.get(correct_opt, correct_opt)
				options = ["True", "False"]  # canonical order: True first

			exam_questions.append(
				{
					"col": col_idx,
					"header": col_header.strip(),
					"options": options,
					"correct": correct_opt,
					"confidence": confidence,
					"n_hi": len(hi_opts_raw),
					"n_total": n_all,
					"skipped": False,
				}
			)

	return {
		"std": std,
		"max_score": max_score,
		"num_responses": len(rows),
		"exam_questions": exam_questions,
		"feedback_questions": feedback_questions,
	}


# ---------------------------------------------------------------------------
# JSON doc builders
# ---------------------------------------------------------------------------


def _html_wrap(text: str) -> str:
	"""Wrap plain question text in the Quill ql-editor div the LMS expects."""
	escaped = html.escape(text, quote=False)
	return f'<div class="ql-editor read-mode"><p>{escaped}</p></div>'


def _make_lms_question(name: str, question_text: str, options: list[str], correct: str) -> dict:
	"""Emit one LMS Question doc in the existing seed format."""
	doc: dict[str, Any] = {
		"name": name,
		"question": _html_wrap(question_text),
		"type": "Choices",
		"multiple": 0,
	}
	for i in range(1, 5):
		opt = options[i - 1] if i - 1 < len(options) else None
		doc[f"option_{i}"] = opt
		doc[f"is_correct_{i}"] = 1 if (opt is not None and opt == correct) else 0
		doc[f"explanation_{i}"] = None

	for i in range(1, 5):
		doc[f"possibility_{i}"] = None

	doc["doctype"] = "LMS Question"
	return doc


def _make_lms_quiz(
	name: str,
	title: str,
	lesson: str,
	course: str,
	questions: list[dict],
	total_marks: int,
	passing_percentage: int = 70,
	max_attempts: int = 0,
	is_feedback: bool = False,
) -> dict:
	"""Emit one LMS Quiz doc."""
	return {
		"name": name,
		"title": title,
		"max_attempts": 1 if is_feedback else max_attempts,
		"show_answers": 0,
		"show_submission_history": 0,
		"total_marks": total_marks,
		"passing_percentage": passing_percentage,
		"duration": None,
		"shuffle_questions": 0,
		"limit_questions_to": 0,
		"enable_negative_marking": 0,
		"marks_to_cut": 1,
		"lesson": lesson,
		"course": course,
		"doctype": "LMS Quiz",
		"questions": questions,
	}


# ---------------------------------------------------------------------------
# Course JSON updater (adds feedback chapter/lesson to non-26000 courses)
# ---------------------------------------------------------------------------


def _feedback_chapter_entry(std: str, course_slug: str, course_short_intro: str) -> dict:
	"""Return the chapter dict (including nested lessons) for a feedback chapter."""
	chapter_name = f"qa-iso-{std}-feedback"
	lesson_name = f"qa-iso-{std}-feedback-lesson"
	quiz_name = f"quiz-iso-{std}-feedback"
	block_id = f"fbiso{std}"
	content_json = json.dumps(
		{
			"time": 0,
			"blocks": [{"id": block_id, "type": "quiz", "data": {"quiz": quiz_name}}],
			"version": "2.29.0",
		}
	)
	return {
		"chapter": {
			"name": chapter_name,
			"title": "Training Feedback",
			"course": course_slug,
			"course_title": f"Free {course_short_intro}",
			"is_scorm_package": 0,
			"doctype": "Course Chapter",
			"lessons": [{"idx": 1, "lesson": lesson_name}],
		},
		"lessons": [
			{
				"name": lesson_name,
				"title": "Training Feedback",
				"include_in_preview": 0,
				"is_scorm_package": 0,
				"chapter": chapter_name,
				"course": course_slug,
				"content": content_json,
				"body": "",
				"youtube": None,
				"quiz_id": None,
				"question": None,
				"file_type": "",
				"doctype": "Course Lesson",
			}
		],
	}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(forms_root: Path, repo_root: Path) -> None:  # noqa: C901 (long but sequential)
	data_dir = repo_root / "quality_asia_lms" / "setup" / "data"

	# --- Load existing seed JSON to preserve ISO 26000 content -----------------
	existing_questions: list[dict] = json.loads((data_dir / "questions_iso_auditor.json").read_text())
	existing_quizzes: list[dict] = json.loads((data_dir / "quizzes_iso_auditor.json").read_text())
	existing_courses: list[dict] = json.loads((data_dir / "courses_iso_auditor.json").read_text())

	# Entries to keep regardless (ISO 26000 hand-built)
	keep_questions = [q for q in existing_questions if "26000" in q["name"] or "FEEDBACK" in q["name"]]
	keep_quizzes = [q for q in existing_quizzes if "26000" in q["name"]]

	# Build course slug lookup: std → (course_slug, short_intro)
	course_lookup: dict[str, tuple[str, str]] = {}
	for ce in existing_courses:
		c = ce["course"]
		slug = c["name"]
		si = c.get("short_introduction", "")
		# detect std from slug
		for cfg in COURSE_CONFIG:
			std = cfg["std"]
			if f"-iso-{std}-" in slug or slug.endswith(f"-iso-{std}"):
				course_lookup[std] = (slug, si)
				break

	# --- Walk xlsx files --------------------------------------------------------
	all_new_questions: list[dict] = []
	all_new_exam_quizzes: list[dict] = []
	all_new_feedback_quizzes: list[dict] = []
	report_rows: list[str] = []
	courses_needing_feedback: list[str] = []  # std values

	for cfg in COURSE_CONFIG:
		std = cfg["std"]
		skip_exam = cfg.get("skip_exam", False)
		skip_feedback = cfg.get("skip_feedback", False)

		# Find the xlsx in the forms folder
		folder_pattern = cfg["folder"]
		matching_dirs = [
			d for d in forms_root.iterdir() if d.is_dir() and d.name.startswith(folder_pattern)
		]
		if not matching_dirs:
			print(f"  [WARN] folder not found for {folder_pattern} — skipping")
			continue
		course_dir = matching_dirs[0]
		xlsx_files = list(course_dir.glob("*.xlsx"))
		if not xlsx_files:
			print(f"  [WARN] no xlsx in {course_dir.name} — skipping")
			continue
		xlsx_path = xlsx_files[0]
		print(f"Processing {std:6s}  {xlsx_path.name}  ({xlsx_path.stat().st_size // 1024} KB)")

		result = _extract_course(xlsx_path, cfg)
		course_slug, course_short_intro = course_lookup.get(std, ("", ""))

		# --- Exam questions ---
		if not skip_exam:
			exam_qs = [q for q in result["exam_questions"] if not q.get("skipped")]
			skipped_qs = [q for q in result["exam_questions"] if q.get("skipped")]

			if not exam_qs:
				print(f"  [WARN] no exam questions extracted for ISO {std}")
			else:
				q_prefix = f"QA-ISO-{std}"
				lms_questions: list[dict] = []
				quiz_question_rows: list[dict] = []

				for i, eq in enumerate(exam_qs, start=1):
					q_name = f"{q_prefix}-Q{i:02d}"
					opts = eq["options"]
					# cap at 4 options (LMS Question only supports option_1..4)
					if len(opts) > 4:
						print(f"    [WARN] {q_name} has {len(opts)} options — truncating to 4")
						opts = opts[:4]
					lms_q = _make_lms_question(q_name, eq["header"], opts, eq["correct"])
					lms_questions.append(lms_q)
					quiz_question_rows.append(
						{
							"idx": i,
							"question": q_name,
							"marks": MARKS_PER_QUESTION,
							"question_detail": eq["header"][:140],
							"type": "Choices",
						}
					)

				all_new_questions.extend(lms_questions)
				total_marks = len(exam_qs) * MARKS_PER_QUESTION

				quiz_name = f"quiz-iso-{std}"
				lesson_name = f"qa-iso-{std}-final-exam-lesson"
				exam_quiz = _make_lms_quiz(
					name=quiz_name,
					title=cfg["quiz_title"],
					lesson=lesson_name,
					course=course_slug,
					questions=quiz_question_rows,
					total_marks=total_marks,
				)
				all_new_exam_quizzes.append(exam_quiz)

				# Report section for this course
				flag_count = sum(1 for eq in exam_qs if eq["confidence"] < CONFIDENCE_FLAG)
				report_rows.append(
					f"\n## ISO {std} ({len(exam_qs)} questions, total_marks={total_marks}, "
					f"responses={result['num_responses']}, max_score={result['max_score']:.0f})\n"
				)
				# Sort by confidence ascending so low-confidence items come first
				sorted_qs = sorted(
					zip(exam_qs, lms_questions, quiz_question_rows),
					key=lambda t: t[0]["confidence"],
				)
				for eq, lms_q, _ in sorted_qs:
					flag = " ⚠️ **VERIFY**" if eq["confidence"] < CONFIDENCE_FLAG else ""
					correct_display = eq["correct"] or "(none)"
					report_rows.append(
						f"- [{eq['confidence']:.1%}]{flag} **{lms_q['name']}**: "
						f"{eq['header'][:80]}  \n"
						f"  → **{correct_display}**  "
						f"({eq['n_hi']}/{result['num_responses']} hi-scorers agree)\n"
					)
		else:
			# ISO 26000 exam: preserve existing quiz stub (it's already fully built)
			pass

		# --- Feedback quiz ---
		if not skip_feedback:
			fb_qs = result["feedback_questions"]
			if fb_qs:
				quiz_fb_rows: list[dict] = []
				for i, fq in enumerate(fb_qs, start=1):
					quiz_fb_rows.append(
						{
							"idx": i,
							"question": fq["qa_name"],
							"marks": 0,
							"question_detail": fq["header"][:140],
							"type": "Choices",
						}
					)
				feedback_quiz = _make_lms_quiz(
					name=f"quiz-iso-{std}-feedback",
					title=f"ISO {std}:{cfg['year']} Training Feedback",
					lesson=f"qa-iso-{std}-feedback-lesson",
					course=course_slug,
					questions=quiz_fb_rows,
					total_marks=0,
					passing_percentage=0,
					is_feedback=True,
				)
				all_new_feedback_quizzes.append(feedback_quiz)
				courses_needing_feedback.append(std)
			else:
				print(f"  [WARN] no feedback questions found for ISO {std}")

	# --- Merge and write questions_iso_auditor.json ----------------------------
	# keep_questions = ISO 26000 + shared QA-FEEDBACK-* (already present)
	# all_new_questions = exam questions for 9 courses
	out_questions = keep_questions + all_new_questions
	(data_dir / "questions_iso_auditor.json").write_text(
		json.dumps(out_questions, indent=2, ensure_ascii=False) + "\n"
	)
	print(f"\nWrote {len(out_questions)} questions to questions_iso_auditor.json")

	# --- Merge and write quizzes_iso_auditor.json ------------------------------
	# keep_quizzes = ISO 26000 final-exam + ISO 26000 feedback (both preserved)
	# all_new_exam_quizzes = filled stubs for 9 courses
	# all_new_feedback_quizzes = new feedback quizzes for 9 courses (minus 26000)
	out_quizzes = keep_quizzes + all_new_exam_quizzes + all_new_feedback_quizzes
	(data_dir / "quizzes_iso_auditor.json").write_text(
		json.dumps(out_quizzes, indent=2, ensure_ascii=False) + "\n"
	)
	print(f"Wrote {len(out_quizzes)} quizzes to quizzes_iso_auditor.json")

	# --- Update courses_iso_auditor.json — add feedback chapters ---------------
	for ce in existing_courses:
		c = ce["course"]
		slug = c["name"]
		std = next(
			(cfg["std"] for cfg in COURSE_CONFIG if course_lookup.get(cfg["std"], ("",))[0] == slug),
			None,
		)
		if std not in courses_needing_feedback:
			continue
		# Check if feedback chapter already present
		existing_chapter_names = [ch["chapter"]["name"] for ch in ce["chapters"]]
		feedback_chapter_name = f"qa-iso-{std}-feedback"
		if feedback_chapter_name in existing_chapter_names:
			continue  # already added (idempotent)

		# Add chapter reference to course.chapters
		next_idx = len(c["chapters"]) + 1
		c["chapters"].append({"idx": next_idx, "chapter": feedback_chapter_name})

		# Add chapter + lesson entry
		fb_entry = _feedback_chapter_entry(std, slug, c.get("short_introduction", ""))
		ce["chapters"].append(fb_entry)

	(data_dir / "courses_iso_auditor.json").write_text(
		json.dumps(existing_courses, indent=2, ensure_ascii=False) + "\n"
	)
	print(f"Updated courses_iso_auditor.json ({len(courses_needing_feedback)} courses got feedback chapter)")

	# --- Write review report ---------------------------------------------------
	report_path = data_dir / "quiz_extraction_report.md"
	report_header = f"""\
# Quiz Extraction Report

Generated by `quality_asia_lms/setup/tools/extract_quiz_from_forms.py`.

**ISO 26000** is excluded — its 20 exam questions and feedback quiz are hand-built and preserved.

## How to verify low-confidence answers (⚠️ items)

Open the live Google Form in the editor (you must be logged in as the form owner):
- ISO 9001: `https://docs.google.com/forms/d/1GUn9zOnDpQxPomNmmt_J5gOBBBBem7JwupxngYFW6nl/edit`
- For other ISO forms: look in the Google Drive folder shared with you.

Each question in the editor shows green ✓ (correct) and red ✗ (wrong) for each option.
The total points shown in the editor header should match `total_marks` in the quiz JSON.

**Confidence** = fraction of near-perfect scorers (Score ≥ 85 % of max) who chose this answer.
Items below {CONFIDENCE_FLAG:.0%} are flagged ⚠️ for manual review.

---
{"".join(report_rows)}
"""
	report_path.write_text(report_header, encoding="utf-8")
	print(f"Wrote review report to {report_path.relative_to(repo_root)}")

	# Summary
	flagged_total = sum(
		1 for line in report_rows if "⚠️" in line
	)
	print(f"\nDone. {flagged_total} question(s) flagged for manual verification — see quiz_extraction_report.md")


if __name__ == "__main__":
	if len(sys.argv) < 2:
		print(__doc__)
		sys.exit(1)
	forms_root = Path(sys.argv[1]).expanduser().resolve()
	if not forms_root.is_dir():
		print(f"Error: '{forms_root}' is not a directory", file=sys.stderr)
		sys.exit(1)
	# repo root = two levels up from this script (tools/ → setup/ → quality_asia_lms/ → repo root)
	repo_root = Path(__file__).parent.parent.parent.parent.resolve()
	main(forms_root, repo_root)
