"""Tests for the JumpCloud identity provider."""

import unittest
from unittest.mock import patch, MagicMock
from providers.jumpcloud import JumpCloudProvider


class TestJumpCloudProvider(unittest.TestCase):
    """Test JumpCloud provider in dry-run mode and with mocked API calls."""

    def setUp(self):
        self.config = {"org_id": "test_org_123"}
        self.employee = {
            "full_name": "Marcus Johnson",
            "email": "marcus@testcompany.com",
            "department": "Design",
            "level": "L3",
            "username": "marcus.johnson",
        }

    @patch.dict("os.environ", {"JUMPCLOUD_API_KEY": "fake_key"})
    def test_dry_run_create_user(self):
        provider = JumpCloudProvider(self.config, dry_run=True)
        result = provider.create_user(self.employee)
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("marcus@testcompany.com", result["details"])

    @patch.dict("os.environ", {"JUMPCLOUD_API_KEY": "fake_key"})
    def test_dry_run_assign_to_group(self):
        provider = JumpCloudProvider(self.config, dry_run=True)
        result = provider.assign_to_group("user123", "design")
        self.assertTrue(result)

    @patch.dict("os.environ", {"JUMPCLOUD_API_KEY": "fake_key"})
    def test_dry_run_deactivate_user(self):
        provider = JumpCloudProvider(self.config, dry_run=True)
        result = provider.deactivate_user("marcus@testcompany.com")
        self.assertEqual(result["status"], "dry_run")

    @patch.dict("os.environ", {"JUMPCLOUD_API_KEY": "fake_key"})
    def test_dry_run_validate_connection(self):
        provider = JumpCloudProvider(self.config, dry_run=True)
        self.assertTrue(provider.validate_connection())

    @patch.dict("os.environ", {"JUMPCLOUD_API_KEY": "fake_key"})
    def test_provider_name(self):
        provider = JumpCloudProvider(self.config, dry_run=True)
        self.assertEqual(provider.get_provider_name(), "JumpCloud")

    @patch("providers.jumpcloud.requests.request")
    @patch.dict("os.environ", {"JUMPCLOUD_API_KEY": "fake_key"})
    def test_create_user_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"_id": "jc_user_456"}
        mock_request.return_value = mock_response

        provider = JumpCloudProvider(self.config, dry_run=False)
        result = provider.create_user(self.employee)
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["user_id"], "jc_user_456")

    @patch("providers.jumpcloud.requests.request")
    @patch.dict("os.environ", {"JUMPCLOUD_API_KEY": "fake_key"})
    def test_create_user_conflict(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_request.return_value = mock_response

        provider = JumpCloudProvider(self.config, dry_run=False)
        result = provider.create_user(self.employee)
        self.assertEqual(result["status"], "already_exists")

    @patch("providers.jumpcloud.requests.request")
    @patch.dict("os.environ", {"JUMPCLOUD_API_KEY": "fake_key"})
    def test_get_user_found(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{
                "_id": "jc_user_456",
                "email": "marcus@testcompany.com",
                "username": "marcus.johnson",
                "firstname": "Marcus",
                "lastname": "Johnson",
                "activated": True,
                "department": "Design",
            }]
        }
        mock_request.return_value = mock_response

        provider = JumpCloudProvider(self.config, dry_run=False)
        result = provider.get_user("marcus@testcompany.com")
        self.assertIsNotNone(result)
        self.assertEqual(result["user_id"], "jc_user_456")

    @patch("providers.jumpcloud.requests.request")
    @patch.dict("os.environ", {"JUMPCLOUD_API_KEY": "fake_key"})
    def test_get_user_not_found(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_request.return_value = mock_response

        provider = JumpCloudProvider(self.config, dry_run=False)
        result = provider.get_user("nobody@testcompany.com")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
