"""JumpCloud identity provider integration.

Uses the JumpCloud Directory Platform API to:
- Create system users
- Bind users to User Groups
- Deactivate users during offboarding
- Look up existing users

JumpCloud's free tier supports up to 10 users and 10 devices,
making it viable for very early-stage startups. The paid tier
scales from there with no feature gating.

Prerequisites:
- JumpCloud account (free tier works)
- API key from Admin Console > API Settings
- Organization ID

API docs: https://docs.jumpcloud.com/api/1.0/index.html
"""

import requests
from providers import BaseProvider
from utils import get_env, generate_temp_password, is_dry_run


class JumpCloudProvider(BaseProvider):
    """JumpCloud Directory Platform integration for user lifecycle management."""

    BASE_URL_V1 = "https://console.jumpcloud.com/api"
    BASE_URL_V2 = "https://console.jumpcloud.com/api/v2"

    def __init__(self, config: dict, dry_run: bool = False):
        super().__init__(config, dry_run)
        self.api_key = get_env("JUMPCLOUD_API_KEY")
        self.org_id = config.get("org_id") or get_env("JUMPCLOUD_ORG_ID", required=False) or ""
        self._headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.org_id:
            self._headers["x-org-id"] = self.org_id

    def _request(self, method: str, url: str, json_data: dict = None) -> requests.Response:
        """Make an authenticated request to the JumpCloud API."""
        response = requests.request(
            method=method, url=url, headers=self._headers, json=json_data, timeout=30
        )
        return response

    def validate_connection(self) -> bool:
        """Verify JumpCloud API access by hitting the systemusers endpoint."""
        if self.dry_run:
            return True
        response = self._request("GET", f"{self.BASE_URL_V1}/systemusers?limit=1")
        if response.status_code == 200:
            return True
        raise ConnectionError(
            f"JumpCloud API validation failed (HTTP {response.status_code}): "
            f"{response.text}"
        )

    def create_user(self, employee_data: dict) -> dict:
        """Create a new system user in JumpCloud.

        Creates the user with:
        - Username derived from full name
        - Email as the primary identifier
        - Temporary password (forced reset on first login)
        - Department stored in user attributes
        """
        name_parts = employee_data["full_name"].split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else name_parts[0]

        user_body = {
            "username": employee_data["username"],
            "email": employee_data["email"],
            "firstname": first_name,
            "lastname": last_name,
            "password": generate_temp_password(),
            "password_never_expires": False,
            "activated": True,
            "department": employee_data["department"],
            "description": f"Level: {employee_data['level']}",
        }

        if self.dry_run:
            return {
                "user_id": employee_data["email"],
                "status": "dry_run",
                "details": f"Would create JumpCloud user: {employee_data['email']}",
            }

        response = self._request(
            "POST", f"{self.BASE_URL_V1}/systemusers", json_data=user_body
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "user_id": data.get("_id", employee_data["email"]),
                "status": "created",
                "details": f"Created JumpCloud user: {employee_data['email']}",
            }
        elif response.status_code == 409:
            return {
                "user_id": employee_data["email"],
                "status": "already_exists",
                "details": f"User already exists in JumpCloud: {employee_data['email']}",
            }
        else:
            return {
                "user_id": employee_data["email"],
                "status": "failed",
                "details": f"Failed to create user (HTTP {response.status_code}): {response.text}",
            }

    def assign_to_group(self, user_id: str, group: str) -> bool:
        """Bind a user to a JumpCloud User Group.

        First resolves the group name to an ID, then creates
        the user-group membership binding.

        Args:
            user_id: JumpCloud system user ID
            group: Group name to bind the user to
        """
        if self.dry_run:
            return True

        # Resolve group name to ID
        group_id = self._get_group_id(group)
        if not group_id:
            return False

        # Create the membership binding
        bind_body = {
            "op": "add",
            "type": "user",
            "id": user_id,
        }
        response = self._request(
            "POST",
            f"{self.BASE_URL_V2}/usergroups/{group_id}/members",
            json_data=bind_body,
        )
        return response.status_code in (200, 201, 204)

    def _get_group_id(self, group_name: str) -> str:
        """Resolve a group name to its JumpCloud group ID."""
        response = self._request("GET", f"{self.BASE_URL_V2}/usergroups")
        if response.status_code != 200:
            return ""
        groups = response.json()
        for g in groups:
            if g.get("name", "").lower() == group_name.lower():
                return g["id"]
        return ""

    def deactivate_user(self, email: str) -> dict:
        """Deactivate a JumpCloud user by setting their account to inactive.

        This suspends the account and revokes access to all bound
        systems and applications.
        """
        if self.dry_run:
            return {
                "status": "dry_run",
                "details": f"Would deactivate JumpCloud user: {email}",
            }

        # Look up user by email
        user = self.get_user(email)
        if user is None:
            return {
                "status": "not_found",
                "details": f"User not found in JumpCloud: {email}",
            }

        user_id = user["user_id"]
        update_body = {"activated": False, "suspended": True}
        response = self._request(
            "PUT",
            f"{self.BASE_URL_V1}/systemusers/{user_id}",
            json_data=update_body,
        )

        if response.status_code == 200:
            return {
                "status": "deactivated",
                "details": f"Deactivated JumpCloud user: {email}",
            }
        return {
            "status": "failed",
            "details": f"Failed to deactivate user (HTTP {response.status_code}): {response.text}",
        }

    def get_user(self, email: str) -> dict:
        """Look up a JumpCloud user by email address."""
        if self.dry_run:
            return {"user_id": email, "email": email, "status": "dry_run"}

        response = self._request(
            "GET",
            f"{self.BASE_URL_V1}/systemusers?filter=email:$eq:{email}",
        )

        if response.status_code != 200:
            return None

        data = response.json()
        results = data.get("results", [])
        if not results:
            return None

        user = results[0]
        return {
            "user_id": user["_id"],
            "email": user.get("email", ""),
            "username": user.get("username", ""),
            "name": f"{user.get('firstname', '')} {user.get('lastname', '')}".strip(),
            "activated": user.get("activated", False),
            "department": user.get("department", ""),
        }

    def get_provider_name(self) -> str:
        return "JumpCloud"
