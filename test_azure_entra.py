"""Tests for the Azure Entra ID provisioner."""

import unittest
from unittest.mock import patch, MagicMock
from cloud_iam.azure_entra import AzureEntraProvisioner


class TestAzureEntraProvisioner(unittest.TestCase):
    """Test Azure Entra ID provisioner in dry-run mode and with mocked API calls."""

    def setUp(self):
        self.employee = {
            "full_name": "Aisha Patel",
            "email": "aisha.patel@testcompany.com",
            "department": "Product",
            "level": "L4",
            "username": "aisha.patel",
        }
        self.role_config = {
            "roles": ["Contributor"],
            "groups": ["product-team"],
        }

    @patch.dict("os.environ", {
        "AZURE_TENANT_ID": "fake_tenant",
        "AZURE_CLIENT_ID": "fake_client",
        "AZURE_CLIENT_SECRET": "fake_secret",
    })
    def test_dry_run_provision(self):
        provisioner = AzureEntraProvisioner(dry_run=True)
        results = provisioner.provision_user(self.employee, self.role_config)
        self.assertTrue(len(results) > 0)
        for r in results:
            self.assertEqual(r["status"], "DRY_RUN")

    @patch.dict("os.environ", {
        "AZURE_TENANT_ID": "fake_tenant",
        "AZURE_CLIENT_ID": "fake_client",
        "AZURE_CLIENT_SECRET": "fake_secret",
    })
    def test_dry_run_deprovision(self):
        provisioner = AzureEntraProvisioner(dry_run=True)
        results = provisioner.deprovision_user("aisha.patel@testcompany.com")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "DRY_RUN")

    @patch.dict("os.environ", {
        "AZURE_TENANT_ID": "fake_tenant",
        "AZURE_CLIENT_ID": "fake_client",
        "AZURE_CLIENT_SECRET": "fake_secret",
    })
    def test_dry_run_validate(self):
        provisioner = AzureEntraProvisioner(dry_run=True)
        self.assertTrue(provisioner.validate_connection())

    @patch("cloud_iam.azure_entra.requests.post")
    @patch("cloud_iam.azure_entra.requests.request")
    @patch.dict("os.environ", {
        "AZURE_TENANT_ID": "fake_tenant",
        "AZURE_CLIENT_ID": "fake_client",
        "AZURE_CLIENT_SECRET": "fake_secret",
    })
    def test_create_user_success(self, mock_request, mock_post):
        # Mock token acquisition
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "fake_token"}
        mock_post.return_value = mock_token_response

        # Mock user creation
        mock_create_response = MagicMock()
        mock_create_response.status_code = 201
        mock_create_response.json.return_value = {"id": "azure_user_789"}

        # Mock group lookup
        mock_group_response = MagicMock()
        mock_group_response.status_code = 200
        mock_group_response.json.return_value = {"value": [{"id": "group_abc"}]}

        # Mock group add
        mock_add_response = MagicMock()
        mock_add_response.status_code = 204

        mock_request.side_effect = [
            mock_create_response,
            mock_group_response,
            mock_add_response,
        ]

        provisioner = AzureEntraProvisioner(dry_run=False)
        results = provisioner.provision_user(self.employee, self.role_config)

        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["status"], "SUCCESS")
        self.assertEqual(results[0]["action"], "CREATE_ENTRA_USER")

    @patch("cloud_iam.azure_entra.requests.post")
    @patch("cloud_iam.azure_entra.requests.request")
    @patch.dict("os.environ", {
        "AZURE_TENANT_ID": "fake_tenant",
        "AZURE_CLIENT_ID": "fake_client",
        "AZURE_CLIENT_SECRET": "fake_secret",
    })
    def test_deprovision_user_not_found(self, mock_request, mock_post):
        # Mock token
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "fake_token"}
        mock_post.return_value = mock_token_response

        # Mock user lookup returning 404
        mock_lookup = MagicMock()
        mock_lookup.status_code = 404
        mock_lookup.json.return_value = {}
        mock_request.return_value = mock_lookup

        provisioner = AzureEntraProvisioner(dry_run=False)
        results = provisioner.deprovision_user("nobody@testcompany.com")
        self.assertEqual(results[0]["status"], "SKIPPED")


if __name__ == "__main__":
    unittest.main()
