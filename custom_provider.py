"""Custom identity provider template.

Use this as a starting point when integrating with an identity provider
not covered by the built-in Google Workspace or JumpCloud integrations.

To add a custom provider:
1. Copy this file and rename it (e.g., onelogin.py)
2. Implement all abstract methods from BaseProvider
3. Register it in the provider router in main.py
4. Add configuration to config/provider_config.json
5. Add required environment variables to .env

Common providers you might integrate:
- OneLogin (https://developers.onelogin.com/api-docs/2/getting-started/dev-overview)
- Auth0 (https://auth0.com/docs/api/management/v2)
- Azure AD / Entra ID (https://learn.microsoft.com/en-us/graph/api/overview)
- Keycloak (https://www.keycloak.org/docs-api/latest/rest-api/index.html)
"""

from providers import BaseProvider


class CustomProvider(BaseProvider):
    """Template for custom identity provider integrations.

    Replace the placeholder implementations below with actual
    API calls to your identity provider.
    """

    def __init__(self, config: dict, dry_run: bool = False):
        super().__init__(config, dry_run)
        # Load your provider-specific config here
        # self.api_key = get_env("YOUR_PROVIDER_API_KEY")
        # self.base_url = config.get("base_url", "https://api.yourprovider.com")

    def validate_connection(self) -> bool:
        """Test connectivity to your identity provider API."""
        raise NotImplementedError(
            "CustomProvider.validate_connection() must be implemented. "
            "Make a lightweight API call (e.g., list users with limit=1) "
            "to verify credentials and connectivity."
        )

    def create_user(self, employee_data: dict) -> dict:
        """Create a user in your identity provider.

        Expected employee_data keys:
            - full_name (str)
            - email (str)
            - department (str)
            - level (str)
            - username (str)

        Must return:
            {
                "user_id": "provider-specific-id",
                "status": "created" | "already_exists" | "failed",
                "details": "Human-readable message"
            }
        """
        raise NotImplementedError(
            "CustomProvider.create_user() must be implemented."
        )

    def assign_to_group(self, user_id: str, group: str) -> bool:
        """Assign a user to a group in your identity provider.

        Returns True on success, False on failure.
        """
        raise NotImplementedError(
            "CustomProvider.assign_to_group() must be implemented."
        )

    def deactivate_user(self, email: str) -> dict:
        """Deactivate/suspend a user in your identity provider.

        Must return:
            {
                "status": "deactivated" | "not_found" | "failed",
                "details": "Human-readable message"
            }
        """
        raise NotImplementedError(
            "CustomProvider.deactivate_user() must be implemented."
        )

    def get_user(self, email: str) -> dict:
        """Look up a user by email. Return None if not found."""
        raise NotImplementedError(
            "CustomProvider.get_user() must be implemented."
        )

    def get_provider_name(self) -> str:
        return "Custom Provider"
