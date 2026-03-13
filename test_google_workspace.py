"""Tests for the Google Workspace identity provider."""

import unittest
from unittest.mock import patch, MagicMock
from providers.google_workspace import GoogleWorkspaceProvider


class TestGoogleWorkspaceProvider(unittest.TestCase):
    """Test Google Workspace provider in dry-run mode and with mocked API calls."""

    def setUp(self):
        self.config = {
            "domain": "testcompany.com",
            "admin_email": "admin@testcompany.com",
            "credentials_file": "fake_creds.json",
            "default_org_unit": "/Employees",
        }
        self.employee = {
            "full_name": "Jane Smith",
            "email": "jane.smith@testcompany.com",
            "department": "Engineering",
            "level": "L4",
            "username": "jane.smith",
        }

    def test_dry_run_create_user(self):
        provider = GoogleWorkspaceProvider(self.config, dry_run=True)
        result = provider.create_user(self.employee)
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("jane.smith@testcompany.com", result["details"])

    def test_dry_run_assign_to_group(self):
        provider = GoogleWorkspaceProvider(self.config, dry_run=True)
        result = provider.assign_to_group("jane.smith@testcompany.com", "engineering")
        self.assertTrue(result)

    def test_dry_run_deactivate_user(self):
        provider = GoogleWorkspaceProvider(self.config, dry_run=True)
        result = provider.deactivate_user("jane.smith@testcompany.com")
        self.assertEqual(result["status"], "dry_run")

    def test_dry_run_validate_connection(self):
        provider = GoogleWorkspaceProvider(self.config, dry_run=True)
        self.assertTrue(provider.validate_connection())

    def test_dry_run_get_user(self):
        provider = GoogleWorkspaceProvider(self.config, dry_run=True)
        result = provider.get_user("jane.smith@testcompany.com")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "dry_run")

    def test_provider_name(self):
        provider = GoogleWorkspaceProvider(self.config, dry_run=True)
        self.assertEqual(provider.get_provider_name(), "Google Workspace")

    @patch("providers.google_workspace.build")
    @patch("providers.google_workspace.service_account")
    def test_create_user_success(self, mock_sa, mock_build):
        mock_creds = MagicMock()
        mock_sa.Credentials.from_service_account_file.return_value = mock_creds
        mock_creds.with_subject.return_value = mock_creds

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.users().insert().execute.return_value = {
            "id": "user123",
            "primaryEmail": "jane.smith@testcompany.com",
        }

        provider = GoogleWorkspaceProvider(self.config, dry_run=False)
        result = provider.create_user(self.employee)
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["user_id"], "user123")

    @patch("providers.google_workspace.build")
    @patch("providers.google_workspace.service_account")
    def test_create_user_already_exists(self, mock_sa, mock_build):
        from googleapiclient.errors import HttpError

        mock_creds = MagicMock()
        mock_sa.Credentials.from_service_account_file.return_value = mock_creds
        mock_creds.with_subject.return_value = mock_creds

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        resp = MagicMock()
        resp.status = 409
        error = HttpError(resp=resp, content=b"Entity already exists")
        mock_service.users().insert().execute.side_effect = error

        provider = GoogleWorkspaceProvider(self.config, dry_run=False)
        result = provider.create_user(self.employee)
        self.assertEqual(result["status"], "already_exists")


if __name__ == "__main__":
    unittest.main()
