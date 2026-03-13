"""Tests for the AWS IAM provisioner."""

import unittest
from unittest.mock import patch, MagicMock
from cloud_iam.aws_iam import AWSIAMProvisioner


class TestAWSIAMProvisioner(unittest.TestCase):
    """Test AWS IAM provisioner in dry-run mode and with mocked boto3 calls."""

    def setUp(self):
        self.employee = {
            "full_name": "Jane Smith",
            "email": "jane.smith@testcompany.com",
            "department": "Engineering",
            "level": "L4",
            "username": "jane.smith",
        }
        self.role_config = {
            "groups": ["engineering-dev", "engineering-deploy"],
            "policies": [
                "arn:aws:iam::aws:policy/PowerUserAccess",
            ],
        }

    def test_dry_run_provision(self):
        provisioner = AWSIAMProvisioner(dry_run=True)
        results = provisioner.provision_user(self.employee, self.role_config)
        self.assertTrue(len(results) > 0)
        for r in results:
            self.assertEqual(r["status"], "DRY_RUN")

    def test_dry_run_deprovision(self):
        provisioner = AWSIAMProvisioner(dry_run=True)
        results = provisioner.deprovision_user("jane.smith")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "DRY_RUN")

    def test_dry_run_validate(self):
        provisioner = AWSIAMProvisioner(dry_run=True)
        self.assertTrue(provisioner.validate_connection())

    @patch("cloud_iam.aws_iam.boto3.client")
    @patch.dict("os.environ", {
        "AWS_ACCESS_KEY_ID": "fake",
        "AWS_SECRET_ACCESS_KEY": "fake",
        "AWS_REGION": "us-east-1",
    })
    def test_create_user_success(self, mock_boto):
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.create_user.return_value = {"User": {"UserName": "jane.smith"}}
        mock_client.create_login_profile.return_value = {}
        mock_client.add_user_to_group.return_value = {}
        mock_client.attach_user_policy.return_value = {}

        provisioner = AWSIAMProvisioner(dry_run=False)
        provisioner._client = mock_client
        results = provisioner.provision_user(self.employee, self.role_config)

        # Should have: create user + login profile + 2 groups + 1 policy = 5 results
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]["status"], "SUCCESS")
        self.assertEqual(results[0]["action"], "CREATE_IAM_USER")

    @patch("cloud_iam.aws_iam.boto3.client")
    @patch.dict("os.environ", {
        "AWS_ACCESS_KEY_ID": "fake",
        "AWS_SECRET_ACCESS_KEY": "fake",
    })
    def test_create_user_already_exists(self, mock_boto):
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_boto.return_value = mock_client

        error_response = {"Error": {"Code": "EntityAlreadyExists", "Message": "exists"}}
        mock_client.create_user.side_effect = ClientError(error_response, "CreateUser")

        provisioner = AWSIAMProvisioner(dry_run=False)
        provisioner._client = mock_client
        result = provisioner._create_user("jane.smith")
        self.assertEqual(result["status"], "SKIPPED")

    @patch("cloud_iam.aws_iam.boto3.client")
    @patch.dict("os.environ", {
        "AWS_ACCESS_KEY_ID": "fake",
        "AWS_SECRET_ACCESS_KEY": "fake",
    })
    def test_deprovision_user_success(self, mock_boto):
        mock_client = MagicMock()
        mock_boto.return_value = mock_client

        mock_client.list_access_keys.return_value = {"AccessKeyMetadata": []}
        mock_client.list_groups_for_user.return_value = {
            "Groups": [{"GroupName": "engineering-dev"}]
        }
        mock_client.list_attached_user_policies.return_value = {
            "AttachedPolicies": [
                {"PolicyName": "PowerUserAccess", "PolicyArn": "arn:aws:iam::aws:policy/PowerUserAccess"}
            ]
        }
        mock_client.remove_user_from_group.return_value = {}
        mock_client.detach_user_policy.return_value = {}
        mock_client.delete_login_profile.return_value = {}
        mock_client.delete_user.return_value = {}

        provisioner = AWSIAMProvisioner(dry_run=False)
        provisioner._client = mock_client
        results = provisioner.deprovision_user("jane.smith")

        actions = [r["action"] for r in results]
        self.assertIn("REMOVE_FROM_IAM_GROUP", actions)
        self.assertIn("DETACH_IAM_POLICY", actions)
        self.assertIn("DELETE_IAM_USER", actions)


if __name__ == "__main__":
    unittest.main()
