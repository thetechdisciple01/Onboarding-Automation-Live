"""Google Workspace identity provider integration.

Uses the Google Admin SDK Directory API to:
- Create users in Google Workspace
- Assign users to Groups and Organizational Units
- Suspend/delete users during offboarding
- Look up existing users

Prerequisites:
- Google Workspace domain with admin privileges
- Service account with domain-wide delegation enabled
- Admin SDK API enabled in Google Cloud Console
- Service account JSON key file

Setup guide: https://developers.google.com/admin-sdk/directory/v1/guides/delegation
"""

from providers import BaseProvider
from utils import get_env, generate_temp_password, is_dry_run

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    service_account = None
    build = None
    HttpError = Exception


class GoogleWorkspaceProvider(BaseProvider):
    """Google Workspace Admin SDK integration for user lifecycle management."""

    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.user",
        "https://www.googleapis.com/auth/admin.directory.group",
        "https://www.googleapis.com/auth/admin.directory.orgunit",
    ]

    def __init__(self, config: dict, dry_run: bool = False):
        super().__init__(config, dry_run)
        self.domain = config.get("domain") or get_env("GOOGLE_DOMAIN")
        self.admin_email = config.get("admin_email") or get_env("GOOGLE_ADMIN_EMAIL")
        self.credentials_file = config.get("credentials_file") or get_env(
            "GOOGLE_CREDENTIALS_FILE"
        )
        self.default_org_unit = config.get("default_org_unit", "/Employees")
        self._service = None

    def _get_service(self):
        """Build and cache the Google Admin SDK service client."""
        if self._service is not None:
            return self._service

        if service_account is None:
            raise ImportError(
                "Google API client libraries not installed. "
                "Run: pip install google-api-python-client google-auth"
            )

        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_file, scopes=self.SCOPES
        )
        delegated_credentials = credentials.with_subject(self.admin_email)
        self._service = build("admin", "directory_v1", credentials=delegated_credentials)
        return self._service

    def validate_connection(self) -> bool:
        """Verify Google Workspace API access by listing a single user."""
        if self.dry_run:
            return True
        try:
            service = self._get_service()
            service.users().list(domain=self.domain, maxResults=1).execute()
            return True
        except HttpError as e:
            raise ConnectionError(
                f"Google Workspace API validation failed: {e.reason}"
            )

    def create_user(self, employee_data: dict) -> dict:
        """Create a new user in Google Workspace.

        Creates the user account with:
        - Primary email based on name and domain
        - Temporary password (forced change on first login)
        - Assigned to the default Organizational Unit
        - Department set in user profile
        """
        email = employee_data["email"]
        name_parts = employee_data["full_name"].split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else name_parts[0]

        user_body = {
            "primaryEmail": email,
            "name": {"givenName": first_name, "familyName": last_name},
            "password": generate_temp_password(),
            "changePasswordAtNextLogin": True,
            "orgUnitPath": self.default_org_unit,
            "organizations": [
                {
                    "department": employee_data["department"],
                    "title": employee_data.get("title", ""),
                    "primary": True,
                }
            ],
        }

        if self.dry_run:
            return {
                "user_id": email,
                "status": "dry_run",
                "details": f"Would create Google Workspace user: {email}",
            }

        try:
            service = self._get_service()
            result = service.users().insert(body=user_body).execute()
            return {
                "user_id": result["id"],
                "status": "created",
                "details": f"Created Google Workspace user: {email}",
            }
        except HttpError as e:
            if e.resp.status == 409:
                return {
                    "user_id": email,
                    "status": "already_exists",
                    "details": f"User already exists in Google Workspace: {email}",
                }
            return {
                "user_id": email,
                "status": "failed",
                "details": f"Failed to create user: {e.reason}",
            }

    def assign_to_group(self, user_id: str, group: str) -> bool:
        """Add user to a Google Group.

        Args:
            user_id: User's email address
            group: Group email address (e.g., engineering@company.com)
        """
        if not group.endswith(f"@{self.domain}"):
            group = f"{group}@{self.domain}"

        member_body = {"email": user_id, "role": "MEMBER"}

        if self.dry_run:
            return True

        try:
            service = self._get_service()
            service.members().insert(groupKey=group, body=member_body).execute()
            return True
        except HttpError as e:
            if e.resp.status == 409:
                return True  # Already a member
            return False

    def deactivate_user(self, email: str) -> dict:
        """Suspend a user account in Google Workspace.

        Suspending (rather than deleting) preserves data and allows
        recovery if needed. The user loses access immediately.
        """
        if self.dry_run:
            return {
                "status": "dry_run",
                "details": f"Would suspend Google Workspace user: {email}",
            }

        try:
            service = self._get_service()
            service.users().update(
                userKey=email, body={"suspended": True}
            ).execute()
            return {
                "status": "deactivated",
                "details": f"Suspended Google Workspace user: {email}",
            }
        except HttpError as e:
            if e.resp.status == 404:
                return {
                    "status": "not_found",
                    "details": f"User not found in Google Workspace: {email}",
                }
            return {
                "status": "failed",
                "details": f"Failed to suspend user: {e.reason}",
            }

    def get_user(self, email: str) -> dict:
        """Look up a user by email in Google Workspace."""
        if self.dry_run:
            return {"email": email, "status": "dry_run"}

        try:
            service = self._get_service()
            user = service.users().get(userKey=email).execute()
            return {
                "user_id": user["id"],
                "email": user["primaryEmail"],
                "name": user["name"]["fullName"],
                "suspended": user.get("suspended", False),
                "org_unit": user.get("orgUnitPath", ""),
            }
        except HttpError as e:
            if e.resp.status == 404:
                return None
            raise

    def get_provider_name(self) -> str:
        return "Google Workspace"
