"""Tests that migrated records suppress emails while normal flows still fire them.

Covers:
  - Migrated certificates (is_migrated=1) never queue emails
  - New certificates for migrated users DO queue emails
  - Migrated users suppress welcome email on insert
  - Normal signup users still get welcome email
  - get_course_outline returns [] for empty/None course (with Referer fallback)
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe


class TestCertificateEmailSuppression(unittest.TestCase):
	"""Verify that QALMSCertificate.send_certification_email respects is_migrated."""

	def _make_cert(self, is_migrated=0):
		from quality_asia_lms.overrides.certificate import QALMSCertificate

		cert = QALMSCertificate.__new__(QALMSCertificate)
		cert.doctype = "LMS Certificate"
		cert.is_migrated = is_migrated
		cert.flags = frappe._dict()
		cert.init_valid_columns = lambda: None
		return cert

	@patch("lms.lms.doctype.lms_certificate.lms_certificate.LMSCertificate.send_certification_email")
	def test_migrated_cert_skips_email(self, mock_parent_send):
		cert = self._make_cert(is_migrated=1)
		cert.send_certification_email()
		mock_parent_send.assert_not_called()

	@patch("lms.lms.doctype.lms_certificate.lms_certificate.LMSCertificate.send_certification_email")
	def test_import_flag_skips_email(self, mock_parent_send):
		cert = self._make_cert(is_migrated=0)
		frappe.flags.in_import = True
		try:
			cert.send_certification_email()
			mock_parent_send.assert_not_called()
		finally:
			frappe.flags.in_import = False

	@patch("lms.lms.doctype.lms_certificate.lms_certificate.LMSCertificate.send_certification_email")
	def test_normal_cert_sends_email(self, mock_parent_send):
		cert = self._make_cert(is_migrated=0)
		frappe.flags.in_import = False
		cert.send_certification_email()
		mock_parent_send.assert_called_once()


class TestWelcomeEmailSuppression(unittest.TestCase):
	"""Verify that suppress_welcome_for_migrated sets the right flags."""

	def test_migrated_user_suppresses_welcome(self):
		from quality_asia_lms.overrides.migrated_users import suppress_welcome_for_migrated

		doc = frappe._dict({
			"doctype": "User",
			"is_migrated": 1,
			"send_welcome_email": 1,
			"flags": frappe._dict(),
		})
		suppress_welcome_for_migrated(doc)
		self.assertTrue(doc.flags.no_welcome_mail)
		self.assertEqual(doc.send_welcome_email, 0)

	def test_normal_user_keeps_welcome(self):
		from quality_asia_lms.overrides.migrated_users import suppress_welcome_for_migrated

		doc = frappe._dict({
			"doctype": "User",
			"is_migrated": 0,
			"send_welcome_email": 1,
			"flags": frappe._dict(),
		})
		suppress_welcome_for_migrated(doc)
		self.assertFalse(doc.flags.get("no_welcome_mail"))
		self.assertEqual(doc.send_welcome_email, 1)

	def test_import_flag_suppresses_welcome(self):
		from quality_asia_lms.overrides.migrated_users import suppress_welcome_for_migrated

		doc = frappe._dict({
			"doctype": "User",
			"is_migrated": 0,
			"send_welcome_email": 1,
			"flags": frappe._dict(),
		})
		frappe.flags.in_import = True
		try:
			suppress_welcome_for_migrated(doc)
			self.assertTrue(doc.flags.no_welcome_mail)
		finally:
			frappe.flags.in_import = False


class TestCourseOutlineGuard(unittest.TestCase):
	"""Verify that get_course_outline returns [] for missing course param and
	falls back to the Referer header when the Vue SPA fires the request before
	the course resource resolves (non-admin race condition).
	"""

	@patch("quality_asia_lms.overrides.course._course_from_referer", return_value=None)
	def test_none_course_no_referer_returns_empty(self, _mock_ref):
		from quality_asia_lms.overrides.course import get_course_outline

		result = get_course_outline(course=None)
		self.assertEqual(result, [])

	@patch("quality_asia_lms.overrides.course._course_from_referer", return_value=None)
	def test_empty_string_no_referer_returns_empty(self, _mock_ref):
		from quality_asia_lms.overrides.course import get_course_outline

		result = get_course_outline(course="")
		self.assertEqual(result, [])

	@patch("quality_asia_lms.overrides.course._original_get_course_outline")
	def test_valid_course_delegates(self, mock_original):
		from quality_asia_lms.overrides.course import get_course_outline

		mock_original.return_value = [{"chapter": "test"}]
		result = get_course_outline(course="TEST-COURSE-001")
		mock_original.assert_called_once_with("TEST-COURSE-001", False)
		self.assertEqual(result, [{"chapter": "test"}])

	@patch("quality_asia_lms.overrides.course._original_get_course_outline")
	@patch("quality_asia_lms.overrides.course._course_from_referer")
	def test_none_course_with_referer_fallback(self, mock_ref, mock_original):
		"""When course is missing but Referer contains a valid slug, delegate."""
		from quality_asia_lms.overrides.course import get_course_outline

		mock_ref.return_value = "iso-26000-2010"
		mock_original.return_value = [{"chapter": "Final Exam"}]
		result = get_course_outline(course=None)
		mock_original.assert_called_once_with("iso-26000-2010", False)
		self.assertEqual(result, [{"chapter": "Final Exam"}])

	@patch("quality_asia_lms.overrides.course._original_get_course_outline")
	def test_explicit_course_ignores_referer(self, mock_original):
		"""When course is explicitly provided, Referer is never consulted."""
		from quality_asia_lms.overrides.course import get_course_outline

		mock_original.return_value = [{"chapter": "test"}]
		result = get_course_outline(course="my-course")
		mock_original.assert_called_once_with("my-course", False)
		self.assertEqual(result, [{"chapter": "test"}])


class TestCourseFromReferer(unittest.TestCase):
	"""Unit tests for _course_from_referer — the Referer URL parser."""

	def _call(self, referer):
		from quality_asia_lms.overrides.course import _course_from_referer

		mock_request = MagicMock()
		mock_request.headers.get.return_value = referer
		with patch.object(frappe, "request", mock_request):
			return _course_from_referer()

	@patch("frappe.db.exists", return_value=True)
	def test_standard_course_url(self, _mock_exists):
		result = self._call("https://school.qualityasia.in/lms/courses/iso-26000-2010")
		self.assertEqual(result, "iso-26000-2010")

	@patch("frappe.db.exists", return_value=True)
	def test_course_url_with_trailing_path(self, _mock_exists):
		result = self._call("https://school.qualityasia.in/lms/courses/my-course/learn/1.1")
		self.assertEqual(result, "my-course")

	@patch("frappe.db.exists", return_value=True)
	def test_course_url_with_query_string(self, _mock_exists):
		result = self._call("https://example.com/lms/courses/my-course?tab=overview")
		self.assertEqual(result, "my-course")

	@patch("frappe.db.exists", return_value=False)
	def test_nonexistent_course_returns_none(self, _mock_exists):
		result = self._call("https://example.com/lms/courses/no-such-course")
		self.assertIsNone(result)

	def test_no_referer_returns_none(self):
		result = self._call(None)
		self.assertIsNone(result)

	def test_non_course_url_returns_none(self):
		result = self._call("https://example.com/lms/batches/some-batch")
		self.assertIsNone(result)

	def test_no_request_object(self):
		from quality_asia_lms.overrides.course import _course_from_referer

		with patch.object(frappe, "request", None):
			result = _course_from_referer()
		self.assertIsNone(result)
