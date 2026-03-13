"""AWS IAM provisioning module.

Handles live IAM user lifecycle:
- Create IAM users
- Add users to IAM groups
- Attach managed policies
- Create login profiles (console access)
- Deactivate users (revoke keys, remove from groups, delete login profile)

Prerequisites:
- AWS credentials with IAM admin permissions
- IAM groups pre-created to match config/iam_roles.json
- boto3 installed

Security note: This module creates real IAM resources. Always test with
--dry-run first and review the audit log before running in production.
"""

import boto3
from botocore.exceptions import ClientError
from utils import get_env, generate_temp_password


class AWSIAMProvisioner:
    """Manages AWS IAM user provisioning and de-provisioning."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._client = None

    def _get_client(self):
        """Build and cache the IAM client."""
        if self._client is not None:
            return self._client
        self._client = boto3.client(
            "iam",
            aws_access_key_id=get_env("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=get_env("AWS_SECRET_ACCESS_KEY"),
            region_name=get_env("AWS_REGION", required=False) or "us-east-1",
        )
        return self._client

    def validate_connection(self) -> bool:
        """Verify AWS IAM access by calling get_user on the current identity."""
        if self.dry_run:
            return True
        try:
            client = self._get_client()
            sts = boto3.client(
                "sts",
                aws_access_key_id=get_env("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=get_env("AWS_SECRET_ACCESS_KEY"),
            )
            sts.get_caller_identity()
            return True
        except ClientError as e:
            raise ConnectionError(f"AWS IAM validation failed: {e}")

    def provision_user(self, employee_data: dict, role_config: dict) -> list:
        """Provision an IAM user with groups and policies.

        Args:
            employee_data: Standardized employee dictionary
            role_config: IAM role configuration from iam_roles.json
                Expected keys: 'groups' (list), 'policies' (list)

        Returns:
            List of action result dictionaries for audit logging
        """
        results = []
        username = employee_data["username"]
        groups = role_config.get("groups", [])
        policies = role_config.get("policies", [])

        # Step 1: Create IAM user
        create_result = self._create_user(username)
        results.append(create_result)
        if create_result["status"] == "failed":
            return results

        # Step 2: Create login profile (console access)
        login_result = self._create_login_profile(username)
        results.append(login_result)

        # Step 3: Add to groups
        for group in groups:
            group_result = self._add_to_group(username, group)
            results.append(group_result)

        # Step 4: Attach managed policies
        for policy_arn in policies:
            policy_result = self._attach_policy(username, policy_arn)
            results.append(policy_result)

        return results

    def _create_user(self, username: str) -> dict:
        """Create an IAM user."""
        if self.dry_run:
            return {
                "action": "CREATE_IAM_USER",
                "target": username,
                "status": "DRY_RUN",
                "details": f"Would create IAM user: {username}",
            }
        try:
            client = self._get_client()
            client.create_user(
                UserName=username,
                Tags=[{"Key": "ManagedBy", "Value": "onboarding-automation"}],
            )
            return {
                "action": "CREATE_IAM_USER",
                "target": username,
                "status": "SUCCESS",
                "details": f"Created IAM user: {username}",
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                return {
                    "action": "CREATE_IAM_USER",
                    "target": username,
                    "status": "SKIPPED",
                    "details": f"IAM user already exists: {username}",
                }
            return {
                "action": "CREATE_IAM_USER",
                "target": username,
                "status": "FAILED",
                "details": f"Failed to create IAM user: {e}",
            }

    def _create_login_profile(self, username: str) -> dict:
        """Create a login profile for console access."""
        if self.dry_run:
            return {
                "action": "CREATE_LOGIN_PROFILE",
                "target": username,
                "status": "DRY_RUN",
                "details": f"Would create console login for: {username}",
            }
        try:
            client = self._get_client()
            client.create_login_profile(
                UserName=username,
                Password=generate_temp_password(),
                PasswordResetRequired=True,
            )
            return {
                "action": "CREATE_LOGIN_PROFILE",
                "target": username,
                "status": "SUCCESS",
                "details": f"Created console login (password reset required): {username}",
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                return {
                    "action": "CREATE_LOGIN_PROFILE",
                    "target": username,
                    "status": "SKIPPED",
                    "details": f"Login profile already exists: {username}",
                }
            return {
                "action": "CREATE_LOGIN_PROFILE",
                "target": username,
                "status": "FAILED",
                "details": f"Failed to create login profile: {e}",
            }

    def _add_to_group(self, username: str, group: str) -> dict:
        """Add IAM user to a group."""
        if self.dry_run:
            return {
                "action": "ADD_TO_IAM_GROUP",
                "target": f"{username} -> {group}",
                "status": "DRY_RUN",
                "details": f"Would add {username} to IAM group: {group}",
            }
        try:
            client = self._get_client()
            client.add_user_to_group(UserName=username, GroupName=group)
            return {
                "action": "ADD_TO_IAM_GROUP",
                "target": f"{username} -> {group}",
                "status": "SUCCESS",
                "details": f"Added {username} to IAM group: {group}",
            }
        except ClientError as e:
            return {
                "action": "ADD_TO_IAM_GROUP",
                "target": f"{username} -> {group}",
                "status": "FAILED",
                "details": f"Failed to add to group: {e}",
            }

    def _attach_policy(self, username: str, policy_arn: str) -> dict:
        """Attach a managed policy to an IAM user."""
        policy_name = policy_arn.split("/")[-1]
        if self.dry_run:
            return {
                "action": "ATTACH_IAM_POLICY",
                "target": f"{username} -> {policy_name}",
                "status": "DRY_RUN",
                "details": f"Would attach {policy_name} to {username}",
            }
        try:
            client = self._get_client()
            client.attach_user_policy(UserName=username, PolicyArn=policy_arn)
            return {
                "action": "ATTACH_IAM_POLICY",
                "target": f"{username} -> {policy_name}",
                "status": "SUCCESS",
                "details": f"Attached {policy_name} to {username}",
            }
        except ClientError as e:
            return {
                "action": "ATTACH_IAM_POLICY",
                "target": f"{username} -> {policy_name}",
                "status": "FAILED",
                "details": f"Failed to attach policy: {e}",
            }

    def deprovision_user(self, username: str) -> list:
        """Fully de-provision an IAM user.

        Follows the revoke-first pattern:
        1. Delete access keys
        2. Remove from all groups
        3. Detach all policies
        4. Delete login profile
        5. Delete the user
        """
        results = []

        if self.dry_run:
            results.append({
                "action": "DEPROVISION_IAM_USER",
                "target": username,
                "status": "DRY_RUN",
                "details": f"Would fully de-provision IAM user: {username}",
            })
            return results

        try:
            client = self._get_client()

            # Delete access keys
            keys = client.list_access_keys(UserName=username).get("AccessKeyMetadata", [])
            for key in keys:
                client.delete_access_key(
                    UserName=username, AccessKeyId=key["AccessKeyId"]
                )
                results.append({
                    "action": "DELETE_ACCESS_KEY",
                    "target": f"{username} -> {key['AccessKeyId']}",
                    "status": "SUCCESS",
                    "details": f"Deleted access key: {key['AccessKeyId']}",
                })

            # Remove from groups
            groups = client.list_groups_for_user(UserName=username).get("Groups", [])
            for group in groups:
                client.remove_user_from_group(
                    UserName=username, GroupName=group["GroupName"]
                )
                results.append({
                    "action": "REMOVE_FROM_IAM_GROUP",
                    "target": f"{username} -> {group['GroupName']}",
                    "status": "SUCCESS",
                    "details": f"Removed from group: {group['GroupName']}",
                })

            # Detach policies
            policies = client.list_attached_user_policies(UserName=username).get(
                "AttachedPolicies", []
            )
            for policy in policies:
                client.detach_user_policy(
                    UserName=username, PolicyArn=policy["PolicyArn"]
                )
                results.append({
                    "action": "DETACH_IAM_POLICY",
                    "target": f"{username} -> {policy['PolicyName']}",
                    "status": "SUCCESS",
                    "details": f"Detached policy: {policy['PolicyName']}",
                })

            # Delete login profile
            try:
                client.delete_login_profile(UserName=username)
                results.append({
                    "action": "DELETE_LOGIN_PROFILE",
                    "target": username,
                    "status": "SUCCESS",
                    "details": "Deleted console login profile",
                })
            except ClientError:
                pass  # No login profile to delete

            # Delete user
            client.delete_user(UserName=username)
            results.append({
                "action": "DELETE_IAM_USER",
                "target": username,
                "status": "SUCCESS",
                "details": f"Deleted IAM user: {username}",
            })

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                results.append({
                    "action": "DEPROVISION_IAM_USER",
                    "target": username,
                    "status": "SKIPPED",
                    "details": f"IAM user not found: {username}",
                })
            else:
                results.append({
                    "action": "DEPROVISION_IAM_USER",
                    "target": username,
                    "status": "FAILED",
                    "details": f"Failed to de-provision: {e}",
                })

        return results
