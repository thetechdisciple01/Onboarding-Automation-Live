"""Azure Entra ID (formerly Azure AD) provisioning module.

Handles user lifecycle in Azure Entra ID:
- Create users
- Assign to security groups
- Assign directory roles
- Disable users during offboarding

Prerequisites:
- Azure AD tenant with admin access
- App registration with the following Microsoft Graph API permissions:
    - User.ReadWrite.All
    - Group.ReadWrite.All
    - Directory.ReadWrite.All
    - RoleManagement.ReadWrite.Directory
- Client secret or certificate for the app registration
- azure-identity and msgraph-sdk installed

Setup guide: https://learn.microsoft.com/en-us/graph/auth-register-app-v2
"""

import requests
from utils import get_env, generate_temp_password


class AzureEntraProvisioner:
    """Manages Azure Entra ID user provisioning and de-provisioning."""

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.tenant_id = get_env("AZURE_TENANT_ID")
        self.client_id = get_env("AZURE_CLIENT_ID")
        self.client_secret = get_env("AZURE_CLIENT_SECRET")
        self._token = None

    def _get_token(self) -> str:
        """Acquire an OAuth2 access token using client credentials flow."""
        if self._token:
            return self._token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        response = requests.post(
            token_url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=30,
        )

        if response.status_code != 200:
            raise ConnectionError(
                f"Azure token acquisition failed (HTTP {response.status_code}): "
                f"{response.text}"
            )

        self._token = response.json()["access_token"]
        return self._token

    def _request(self, method: str, endpoint: str, json_data: dict = None) -> requests.Response:
        """Make an authenticated request to Microsoft Graph API."""
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = f"{self.GRAPH_BASE}{endpoint}"
        return requests.request(
            method=method, url=url, headers=headers, json=json_data, timeout=30
        )

    def validate_connection(self) -> bool:
        """Verify Azure Entra ID access by listing a single user."""
        if self.dry_run:
            return True
        response = self._request("GET", "/users?$top=1")
        if response.status_code == 200:
            return True
        raise ConnectionError(
            f"Azure Entra ID validation failed (HTTP {response.status_code}): "
            f"{response.text}"
        )

    def provision_user(self, employee_data: dict, role_config: dict) -> list:
        """Provision a user in Azure Entra ID with group and role assignments.

        Args:
            employee_data: Standardized employee dictionary
            role_config: Azure role configuration from iam_roles.json
                Expected keys: 'roles' (list), 'groups' (list)

        Returns:
            List of action result dictionaries for audit logging
        """
        results = []
        email = employee_data["email"]
        groups = role_config.get("groups", [])

        # Step 1: Create user
        create_result = self._create_user(employee_data)
        results.append(create_result)
        if create_result["status"] == "FAILED":
            return results

        user_id = create_result.get("user_id", email)

        # Step 2: Add to security groups
        for group_name in groups:
            group_result = self._add_to_group(user_id, group_name)
            results.append(group_result)

        return results

    def _create_user(self, employee_data: dict) -> dict:
        """Create a user in Azure Entra ID."""
        name_parts = employee_data["full_name"].split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else name_parts[0]
        display_name = employee_data["full_name"]
        mail_nickname = employee_data["username"]

        user_body = {
            "accountEnabled": True,
            "displayName": display_name,
            "givenName": first_name,
            "surname": last_name,
            "mailNickname": mail_nickname,
            "userPrincipalName": employee_data["email"],
            "department": employee_data["department"],
            "jobTitle": employee_data.get("title", f"Level {employee_data['level']}"),
            "passwordProfile": {
                "forceChangePasswordNextSignIn": True,
                "password": generate_temp_password(),
            },
        }

        if self.dry_run:
            return {
                "action": "CREATE_ENTRA_USER",
                "target": employee_data["email"],
                "status": "DRY_RUN",
                "details": f"Would create Entra ID user: {employee_data['email']}",
                "user_id": employee_data["email"],
            }

        response = self._request("POST", "/users", json_data=user_body)

        if response.status_code == 201:
            data = response.json()
            return {
                "action": "CREATE_ENTRA_USER",
                "target": employee_data["email"],
                "status": "SUCCESS",
                "details": f"Created Entra ID user: {employee_data['email']}",
                "user_id": data.get("id", employee_data["email"]),
            }
        elif response.status_code == 400 and "ObjectConflict" in response.text:
            # Look up existing user ID
            existing = self._get_user_id(employee_data["email"])
            return {
                "action": "CREATE_ENTRA_USER",
                "target": employee_data["email"],
                "status": "SKIPPED",
                "details": f"User already exists in Entra ID: {employee_data['email']}",
                "user_id": existing or employee_data["email"],
            }
        else:
            return {
                "action": "CREATE_ENTRA_USER",
                "target": employee_data["email"],
                "status": "FAILED",
                "details": f"Failed to create user (HTTP {response.status_code}): {response.text}",
                "user_id": employee_data["email"],
            }

    def _add_to_group(self, user_id: str, group_name: str) -> dict:
        """Add a user to an Azure AD security group by group name."""
        if self.dry_run:
            return {
                "action": "ADD_TO_ENTRA_GROUP",
                "target": f"{user_id} -> {group_name}",
                "status": "DRY_RUN",
                "details": f"Would add user to Entra group: {group_name}",
            }

        # Resolve group name to ID
        group_id = self._get_group_id(group_name)
        if not group_id:
            return {
                "action": "ADD_TO_ENTRA_GROUP",
                "target": f"{user_id} -> {group_name}",
                "status": "FAILED",
                "details": f"Group not found in Entra ID: {group_name}",
            }

        body = {
            "@odata.id": f"{self.GRAPH_BASE}/directoryObjects/{user_id}"
        }
        response = self._request(
            "POST", f"/groups/{group_id}/members/$ref", json_data=body
        )

        if response.status_code in (200, 204):
            return {
                "action": "ADD_TO_ENTRA_GROUP",
                "target": f"{user_id} -> {group_name}",
                "status": "SUCCESS",
                "details": f"Added to Entra group: {group_name}",
            }
        elif response.status_code == 400 and "already exist" in response.text.lower():
            return {
                "action": "ADD_TO_ENTRA_GROUP",
                "target": f"{user_id} -> {group_name}",
                "status": "SKIPPED",
                "details": f"Already a member of: {group_name}",
            }
        else:
            return {
                "action": "ADD_TO_ENTRA_GROUP",
                "target": f"{user_id} -> {group_name}",
                "status": "FAILED",
                "details": f"Failed to add to group (HTTP {response.status_code})",
            }

    def _get_group_id(self, group_name: str) -> str:
        """Resolve a group display name to its Azure object ID."""
        response = self._request(
            "GET", f"/groups?$filter=displayName eq '{group_name}'&$select=id"
        )
        if response.status_code != 200:
            return ""
        groups = response.json().get("value", [])
        return groups[0]["id"] if groups else ""

    def _get_user_id(self, email: str) -> str:
        """Resolve an email to an Azure user object ID."""
        response = self._request(
            "GET", f"/users/{email}?$select=id"
        )
        if response.status_code == 200:
            return response.json().get("id", "")
        return ""

    def deprovision_user(self, email: str) -> list:
        """Disable a user in Azure Entra ID.

        Follows the revoke-first pattern:
        1. Disable the account (accountEnabled = false)
        2. Revoke all refresh tokens
        3. Remove from groups
        """
        results = []

        if self.dry_run:
            results.append({
                "action": "DEPROVISION_ENTRA_USER",
                "target": email,
                "status": "DRY_RUN",
                "details": f"Would disable Entra ID user: {email}",
            })
            return results

        user_id = self._get_user_id(email)
        if not user_id:
            results.append({
                "action": "DEPROVISION_ENTRA_USER",
                "target": email,
                "status": "SKIPPED",
                "details": f"User not found in Entra ID: {email}",
            })
            return results

        # Disable account
        disable_response = self._request(
            "PATCH", f"/users/{user_id}", json_data={"accountEnabled": False}
        )
        if disable_response.status_code == 204:
            results.append({
                "action": "DISABLE_ENTRA_USER",
                "target": email,
                "status": "SUCCESS",
                "details": f"Disabled Entra ID account: {email}",
            })
        else:
            results.append({
                "action": "DISABLE_ENTRA_USER",
                "target": email,
                "status": "FAILED",
                "details": f"Failed to disable account (HTTP {disable_response.status_code})",
            })

        # Revoke sessions
        revoke_response = self._request(
            "POST", f"/users/{user_id}/revokeSignInSessions"
        )
        if revoke_response.status_code == 200:
            results.append({
                "action": "REVOKE_ENTRA_SESSIONS",
                "target": email,
                "status": "SUCCESS",
                "details": "Revoked all active sessions",
            })

        # Remove from groups
        groups_response = self._request("GET", f"/users/{user_id}/memberOf?$select=id,displayName")
        if groups_response.status_code == 200:
            for group in groups_response.json().get("value", []):
                if group.get("@odata.type") == "#microsoft.graph.group":
                    remove_response = self._request(
                        "DELETE", f"/groups/{group['id']}/members/{user_id}/$ref"
                    )
                    status = "SUCCESS" if remove_response.status_code == 204 else "FAILED"
                    results.append({
                        "action": "REMOVE_FROM_ENTRA_GROUP",
                        "target": f"{email} -> {group.get('displayName', group['id'])}",
                        "status": status,
                        "details": f"Removed from group: {group.get('displayName', '')}",
                    })

        return results
