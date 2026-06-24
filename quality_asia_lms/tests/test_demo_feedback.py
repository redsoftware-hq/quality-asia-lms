"""Tests for QA-51 demo feedback features.

Covers:
  1. Certification email template — fixture validity, send_mail uses it
  2. Payment dedup — _cleanup_pending_payments removes stale rows
  3. Invoice on_payment_update — idempotency guards
  4. Brand injection — qa_lms_ui.js included in tag block
  5. Property Setter fixture — source reqd=0 present
  6. Email template setup — ensure_certification_template idempotency
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import frappe


# ---------------------------------------------------------------------------
# 1. Email Template fixture
# ---------------------------------------------------------------------------

class TestCertEmailTemplateFixture(unittest.TestCase):
	"""Verify the shipped Email Template fixture is well-formed."""

	@classmethod
	def setUpClass(cls):
		fixture_path = frappe.get_app_path(
			"quality_asia_lms", "fixtures", "email_template.json"
		)
		with open(fixture_path) as f:
			cls.fixtures = json.load(f)

	def test_fixture_is_list_with_one_entry(self):
		self.assertIsInstance(self.fixtures, list)
		self.assertEqual(len(self.fixtures), 1)

	def test_fixture_has_required_fields(self):
		tpl = self.fixtures[0]
		self.assertEqual(tpl["doctype"], "Email Template")
		self.assertEqual(tpl["name"], "QA Certification Email")
		self.assertIn("{{ member_name }}", tpl["response_html"])
		self.assertIn("{{ course_title }}", tpl["response_html"])
		self.assertIn("{{ course_title }}", tpl["subject"])

	def test_fixture_contains_social_links(self):
		html = self.fixtures[0]["response_html"]
		self.assertIn("whatsapp.com/channel/", html)
		self.assertIn("youtube.com/@QualityAsia", html)
		self.assertIn("instagram.com/qualityasia", html)
		self.assertIn("linkedin.com/company/quality-asia", html)

	def test_fixture_uses_dynamic_school_url(self):
		html = self.fixtures[0]["response_html"]
		self.assertIn("frappe.utils.get_url()", html)
		self.assertNotIn("qualityasia.in/qasia-school", html)


class TestCertSendMailUsesCustomTemplate(unittest.TestCase):
	"""Verify QALMSCertificate.send_mail renders the custom template when set."""

	def _make_cert(self):
		from quality_asia_lms.overrides.certificate import QALMSCertificate

		cert = QALMSCertificate.__new__(QALMSCertificate)
		cert.doctype = "LMS Certificate"
		cert.name = "IAC-99999"
		cert.member = "test@example.com"
		cert.member_name = "Test User"
		cert.course = "TEST-COURSE"
		cert.template = "QA Certificate"
		cert.flags = frappe._dict()
		cert.init_valid_columns = lambda: None
		return cert

	@patch("quality_asia_lms.overrides.certificate.frappe.sendmail")
	@patch("quality_asia_lms.overrides.certificate.QALMSCertificate._certificate_pdf_attachment", return_value=[])
	@patch("quality_asia_lms.overrides.certificate.frappe.db.get_value", return_value="ISO 42001:2023")
	@patch(
		"quality_asia_lms.overrides.certificate.frappe.db.get_single_value",
		return_value="QA Certification Email",
	)
	@patch(
		"frappe.email.doctype.email_template.email_template.get_email_template",
		return_value={"subject": "Custom Subject", "message": "<p>Custom body</p>"},
	)
	def test_send_mail_uses_custom_template(
		self, mock_get_tpl, mock_single, mock_get_val, mock_attach, mock_sendmail
	):
		cert = self._make_cert()
		cert.send_mail()

		mock_get_tpl.assert_called_once()
		mock_sendmail.assert_called_once()
		call_kwargs = mock_sendmail.call_args
		self.assertEqual(call_kwargs.kwargs.get("subject") or call_kwargs[1].get("subject"), "Custom Subject")

	@patch("quality_asia_lms.overrides.certificate.frappe.sendmail")
	@patch("quality_asia_lms.overrides.certificate.QALMSCertificate._certificate_pdf_attachment", return_value=[])
	@patch("quality_asia_lms.overrides.certificate.frappe.db.get_value", return_value="ISO 42001:2023")
	@patch(
		"quality_asia_lms.overrides.certificate.frappe.db.get_single_value",
		return_value=None,
	)
	def test_send_mail_falls_back_to_builtin(self, mock_single, mock_get_val, mock_attach, mock_sendmail):
		cert = self._make_cert()
		cert.send_mail()

		mock_sendmail.assert_called_once()
		call_kwargs = mock_sendmail.call_args
		self.assertEqual(
			call_kwargs.kwargs.get("template") or call_kwargs[1].get("template"),
			"certification",
		)


# ---------------------------------------------------------------------------
# 2. Payment dedup
# ---------------------------------------------------------------------------

class TestPaymentDedup(unittest.TestCase):
	"""Verify _cleanup_pending_payments deletes stale unpaid rows only."""

	@patch("quality_asia_lms.overrides.payments.frappe.delete_doc")
	@patch(
		"quality_asia_lms.overrides.payments.frappe.get_all",
		return_value=["PAY-STALE-001", "PAY-STALE-002"],
	)
	@patch("quality_asia_lms.overrides.payments.frappe.session", frappe._dict(user="test@example.com"))
	def test_deletes_stale_rows(self, mock_get_all, mock_delete):
		from quality_asia_lms.overrides.payments import _cleanup_pending_payments

		_cleanup_pending_payments("LMS Course", "COURSE-001")

		mock_get_all.assert_called_once()
		filters = mock_get_all.call_args.kwargs.get("filters") or mock_get_all.call_args[1].get("filters")
		self.assertEqual(filters["member"], "test@example.com")
		self.assertEqual(filters["payment_received"], 0)
		self.assertEqual(mock_delete.call_count, 2)

	@patch("quality_asia_lms.overrides.payments.frappe.delete_doc")
	@patch("quality_asia_lms.overrides.payments.frappe.get_all", return_value=[])
	@patch("quality_asia_lms.overrides.payments.frappe.session", frappe._dict(user="test@example.com"))
	def test_no_stale_rows_no_delete(self, mock_get_all, mock_delete):
		from quality_asia_lms.overrides.payments import _cleanup_pending_payments

		_cleanup_pending_payments("LMS Course", "COURSE-001")
		mock_delete.assert_not_called()

	@patch("quality_asia_lms.overrides.payments.frappe.log_error")
	@patch(
		"quality_asia_lms.overrides.payments.frappe.get_all",
		side_effect=Exception("DB down"),
	)
	@patch("quality_asia_lms.overrides.payments.frappe.session", frappe._dict(user="test@example.com"))
	def test_exception_does_not_propagate(self, mock_get_all, mock_log):
		from quality_asia_lms.overrides.payments import _cleanup_pending_payments

		_cleanup_pending_payments("LMS Course", "COURSE-001")
		mock_log.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Invoice idempotency
# ---------------------------------------------------------------------------

class TestInvoiceIdempotency(unittest.TestCase):
	"""Verify on_payment_update guards against double-invoice."""

	def _make_payment(self, received=True, invoice_number=None):
		doc = frappe._dict({
			"doctype": "LMS Payment",
			"name": "PAY-TEST-001",
			"payment_received": 1 if received else 0,
			"invoice_number": invoice_number,
			"member": "test@example.com",
			"billing_name": "Test User",
			"creation": "2026-06-23",
			"payment_for_document": "COURSE-001",
			"payment_for_document_type": "LMS Course",
		})
		doc.get = lambda key, default=None: doc.get(key, default) if hasattr(doc, key) else getattr(doc, key, default)
		return doc

	@patch("quality_asia_lms.overrides.invoice.frappe.enqueue")
	@patch("quality_asia_lms.overrides.invoice._generate_invoice_number", return_value="B2C/26-27/000001")
	@patch("quality_asia_lms.overrides.invoice.frappe.db.set_value")
	def test_paid_without_invoice_generates(self, mock_set, mock_gen, mock_enq):
		from quality_asia_lms.overrides.invoice import on_payment_update

		doc = self._make_payment(received=True, invoice_number=None)
		on_payment_update(doc)

		mock_gen.assert_called_once()
		mock_enq.assert_called_once()

	@patch("quality_asia_lms.overrides.invoice.frappe.enqueue")
	@patch("quality_asia_lms.overrides.invoice._generate_invoice_number")
	def test_already_invoiced_skips(self, mock_gen, mock_enq):
		from quality_asia_lms.overrides.invoice import on_payment_update

		doc = self._make_payment(received=True, invoice_number="B2C/26-27/000001")
		on_payment_update(doc)

		mock_gen.assert_not_called()
		mock_enq.assert_not_called()

	@patch("quality_asia_lms.overrides.invoice.frappe.enqueue")
	@patch("quality_asia_lms.overrides.invoice._generate_invoice_number")
	def test_unpaid_skips(self, mock_gen, mock_enq):
		from quality_asia_lms.overrides.invoice import on_payment_update

		doc = self._make_payment(received=False)
		on_payment_update(doc)

		mock_gen.assert_not_called()
		mock_enq.assert_not_called()

	@patch("quality_asia_lms.overrides.invoice.frappe.enqueue")
	@patch("quality_asia_lms.overrides.invoice._generate_invoice_number", return_value="B2C/26-27/000001")
	@patch("quality_asia_lms.overrides.invoice.frappe.db.set_value")
	def test_enqueued_kwargs_match_target_signature(self, mock_set, mock_gen, mock_enq):
		"""Regression: ensure enqueue kwargs are accepted by _send_invoice_email.

		Commit f2fdf0f passed user='Administrator' to frappe.enqueue, which
		forwarded it as a kwarg to _send_invoice_email — causing a TypeError
		in production.  This test binds the kwargs against the real function
		signature so a mismatch is caught at test time.
		"""
		import inspect

		from quality_asia_lms.overrides.invoice import _send_invoice_email, on_payment_update

		doc = self._make_payment(received=True, invoice_number=None)
		on_payment_update(doc)

		mock_enq.assert_called_once()
		call_kwargs = mock_enq.call_args

		# The first positional arg is the method itself; the rest are enqueue
		# control kwargs (queue, enqueue_after_commit) plus method kwargs.
		enqueue_control_keys = {"queue", "enqueue_after_commit"}
		method_kwargs = {k: v for k, v in call_kwargs.kwargs.items() if k not in enqueue_control_keys}

		sig = inspect.signature(_send_invoice_email)
		# This raises TypeError if any kwarg is not in the function's signature
		sig.bind(**method_kwargs)


# ---------------------------------------------------------------------------
# 4. Brand injection includes qa_lms_ui.js
# ---------------------------------------------------------------------------

class TestBrandInjection(unittest.TestCase):
	"""Verify brand.py injects all three assets into the SPA shell."""

	MOCK_HTML = (
		'<html><head><link href="/assets/lms/frontend/main.js"></head>'
		"<body></body></html>"
	)

	def test_inject_tags_adds_all_three_assets(self):
		from quality_asia_lms.brand import (
			BRAND_CSS_HREF,
			LMS_UI_JS_HREF,
			PROFILE_JS_HREF,
			_inject_tags,
		)

		result = _inject_tags(self.MOCK_HTML)
		self.assertIsNotNone(result)
		self.assertIn(BRAND_CSS_HREF, result)
		self.assertIn(PROFILE_JS_HREF, result)
		self.assertIn(LMS_UI_JS_HREF, result)

	def test_already_injected_returns_none(self):
		from quality_asia_lms.brand import _inject_tags

		result = _inject_tags(self.MOCK_HTML)
		second = _inject_tags(result)
		self.assertIsNone(second)

	def test_partial_injection_re_injects_all(self):
		from quality_asia_lms.brand import (
			BRAND_CSS_HREF,
			LMS_UI_JS_HREF,
			PROFILE_JS_HREF,
			_inject_tags,
		)

		partial = self.MOCK_HTML.replace(
			"</head>",
			f'<link rel="stylesheet" href="{BRAND_CSS_HREF}">'
			f'<script defer src="{PROFILE_JS_HREF}"></script>'
			"</head>",
		)
		result = _inject_tags(partial)
		self.assertIsNotNone(result)
		self.assertIn(LMS_UI_JS_HREF, result)


# ---------------------------------------------------------------------------
# 5. Property Setter fixture
# ---------------------------------------------------------------------------

class TestPropertySetterFixture(unittest.TestCase):
	"""Verify the source-reqd Property Setter is in the fixture file."""

	@classmethod
	def setUpClass(cls):
		fixture_path = frappe.get_app_path(
			"quality_asia_lms", "fixtures", "property_setter.json"
		)
		with open(fixture_path) as f:
			cls.fixtures = json.load(f)

	def test_source_reqd_setter_exists(self):
		names = [f["name"] for f in self.fixtures]
		self.assertIn("LMS Payment-source-reqd", names)

	def test_source_reqd_is_zero(self):
		setter = next(f for f in self.fixtures if f["name"] == "LMS Payment-source-reqd")
		self.assertEqual(setter["value"], "0")
		self.assertEqual(setter["field_name"], "source")
		self.assertEqual(setter["property"], "reqd")


# ---------------------------------------------------------------------------
# 6. Email template setup idempotency
# ---------------------------------------------------------------------------

class TestEnsureCertificationTemplate(unittest.TestCase):
	"""Verify ensure_certification_template is idempotent."""

	@patch("quality_asia_lms.setup.email_templates.frappe.db.commit")
	@patch("quality_asia_lms.setup.email_templates.frappe.db.set_single_value")
	@patch(
		"quality_asia_lms.setup.email_templates.frappe.db.get_single_value",
		return_value=None,
	)
	@patch("quality_asia_lms.setup.email_templates.frappe.db.exists", return_value=True)
	def test_sets_template_when_empty(self, mock_exists, mock_get, mock_set, mock_commit):
		from quality_asia_lms.setup.email_templates import ensure_certification_template

		ensure_certification_template()
		mock_set.assert_called_once_with(
			"LMS Settings", "certification_template", "QA Certification Email"
		)

	@patch("quality_asia_lms.setup.email_templates.frappe.db.set_single_value")
	@patch(
		"quality_asia_lms.setup.email_templates.frappe.db.get_single_value",
		return_value="Some Other Template",
	)
	@patch("quality_asia_lms.setup.email_templates.frappe.db.exists", return_value=True)
	def test_does_not_overwrite_existing(self, mock_exists, mock_get, mock_set):
		from quality_asia_lms.setup.email_templates import ensure_certification_template

		ensure_certification_template()
		mock_set.assert_not_called()

	@patch("quality_asia_lms.setup.email_templates.frappe.db.set_single_value")
	@patch("quality_asia_lms.setup.email_templates.frappe.db.exists", return_value=False)
	def test_skips_if_template_missing(self, mock_exists, mock_set):
		from quality_asia_lms.setup.email_templates import ensure_certification_template

		ensure_certification_template()
		mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Cleanup orphan patch logic
# ---------------------------------------------------------------------------

class TestCleanupOrphanPatch(unittest.TestCase):
	"""Verify the orphan cleanup patch only deletes confirmed orphans."""

	@patch("quality_asia_lms.patches.v1_0.cleanup_orphan_payments.frappe.db.commit")
	@patch("quality_asia_lms.patches.v1_0.cleanup_orphan_payments.frappe.delete_doc")
	@patch(
		"quality_asia_lms.patches.v1_0.cleanup_orphan_payments.frappe.get_all",
		return_value=["PAY-ORPHAN-001"],
	)
	@patch(
		"quality_asia_lms.patches.v1_0.cleanup_orphan_payments.frappe.db.sql",
		return_value=[
			frappe._dict(member="u@test.com", payment_for_document_type="LMS Course", payment_for_document="C1")
		],
	)
	def test_deletes_orphans_with_paid_sibling(self, mock_sql, mock_get_all, mock_delete, mock_commit):
		from quality_asia_lms.patches.v1_0.cleanup_orphan_payments import execute

		execute()

		mock_delete.assert_called_once_with("LMS Payment", "PAY-ORPHAN-001", ignore_permissions=True, force=True)
		mock_commit.assert_called_once()

	@patch("quality_asia_lms.patches.v1_0.cleanup_orphan_payments.frappe.db.commit")
	@patch("quality_asia_lms.patches.v1_0.cleanup_orphan_payments.frappe.delete_doc")
	@patch(
		"quality_asia_lms.patches.v1_0.cleanup_orphan_payments.frappe.db.sql",
		return_value=[],
	)
	def test_no_paid_rows_no_deletes(self, mock_sql, mock_delete, mock_commit):
		from quality_asia_lms.patches.v1_0.cleanup_orphan_payments import execute

		execute()
		mock_delete.assert_not_called()
		mock_commit.assert_not_called()
