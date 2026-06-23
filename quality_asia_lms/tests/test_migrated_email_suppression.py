"""Tests that migrated records suppress emails while normal flows still fire them.

Covers:
  - Migrated certificates (is_migrated=1) never queue emails
  - New certificates for migrated users DO queue emails
  - Migrated users suppress welcome email on insert
  - Normal signup users still get welcome email
  - get_course_outline returns [] for empty/None course
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
	"""Verify that get_course_outline returns [] for missing course param."""

	def test_none_course_returns_empty(self):
		from quality_asia_lms.overrides.course import get_course_outline

		result = get_course_outline(course=None)
		self.assertEqual(result, [])

	def test_empty_string_returns_empty(self):
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
