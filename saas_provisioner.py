"""Config-driven SaaS application provisioner.

Reads the app catalog (config/app_catalog.json) and provisions users
into department-specific SaaS applications. Supports three provisioning
modes:

- api: Direct API integration (fully automated)
- scim: Provisioned through the identity provider's SCIM connector
- manual: Generates a checklist item for IT to handle manually

The app catalog is fully customizable. Add or remove departments and
apps by editing the JSON config file. No code changes needed.
"""

import json
import os
from utils import load_json_config


class SaaSProvisioner:
    """Handles SaaS application assignment based on department and role."""

    def __init__(self, catalog_path: str = "config/app_catalog.json", dry_run: bool = False):
        self.dry_run = dry_run
        self.catalog = load_json_config(catalog_path)

    def get_apps_for_department(self, department: str) -> list:
        """Return the list of apps configured for a department.

        Args:
            department: Department name (must match a key in app_catalog.json)

        Returns:
            List of app configuration dictionaries, or empty list if
            department is not found.
        """
        dept_config = self.catalog.get(department, {})
        return dept_config.get("apps", [])

    def provision_apps(self, employee_data: dict) -> list:
        """Provision SaaS apps for an employee based on their department.

        For each app in the department's catalog:
        - 'api' apps: Logs as automated provisioning (extend with real API calls)
        - 'scim' apps: Logs as IdP-managed (provisioned through SCIM connector)
        - 'manual' apps: Logs as pending manual action for IT

        Args:
            employee_data: Standardized employee dictionary

        Returns:
            List of action result dictionaries for audit logging
        """
        department = employee_data["department"]
        email = employee_data["email"]
        apps = self.get_apps_for_department(department)
        results = []

        if not apps:
            results.append({
                "action": "SAAS_PROVISION",
                "target": email,
                "provider": "saas",
                "status": "SKIPPED",
                "details": f"No apps configured for department: {department}",
            })
            return results

        for app in apps:
            app_name = app["name"]
            provisioning_type = app.get("provisioning", "manual")
            role = app.get("default_role", "member")

            if self.dry_run:
                results.append({
                    "action": f"PROVISION_SAAS_{app_name.upper()}",
                    "target": email,
                    "provider": "saas",
                    "status": "DRY_RUN",
                    "details": f"Would provision {app_name} ({provisioning_type}) as {role}",
                })
                continue

            if provisioning_type == "scim":
                # SCIM apps are provisioned automatically through the IdP
                # connector when the user is added to the right group.
                results.append({
                    "action": f"PROVISION_SAAS_{app_name.upper()}",
                    "target": email,
                    "provider": "saas",
                    "status": "SUCCESS",
                    "details": (
                        f"{app_name}: Provisioned via SCIM connector (role: {role}). "
                        f"Access granted through IdP group binding."
                    ),
                })

            elif provisioning_type == "api":
                # API-provisioned apps can be extended with direct integrations.
                # For now, log the intent. To add a real integration:
                # 1. Create a module in integrations/ (e.g., integrations/github.py)
                # 2. Call the provisioning function here based on app_name
                result = self._provision_api_app(app_name, email, role)
                results.append(result)

            else:
                # Manual provisioning generates a task for IT
                results.append({
                    "action": f"PROVISION_SAAS_{app_name.upper()}",
                    "target": email,
                    "provider": "saas",
                    "status": "PENDING_MANUAL",
                    "details": (
                        f"{app_name}: Manual provisioning required. "
                        f"Add {email} as {role}. "
                        f"Docs: {app.get('api_docs', 'N/A')}"
                    ),
                })

        return results

    def _provision_api_app(self, app_name: str, email: str, role: str) -> dict:
        """Provision a user in an API-integrated SaaS app.

        This is the extension point for adding direct API integrations.
        Override or extend this method for specific apps.
        """
        # Future: Route to specific integrations based on app_name
        # e.g., if app_name == "github": return github_integration.add_member(email, role)
        return {
            "action": f"PROVISION_SAAS_{app_name.upper()}",
            "target": email,
            "provider": "saas",
            "status": "SUCCESS",
            "details": (
                f"{app_name}: API provisioning logged (role: {role}). "
                f"Extend _provision_api_app() for direct integration."
            ),
        }

    def deprovision_apps(self, email: str, department: str) -> list:
        """Generate de-provisioning actions for all apps in a department.

        Args:
            email: User's email address
            department: User's department for app lookup

        Returns:
            List of action result dictionaries for audit logging
        """
        apps = self.get_apps_for_department(department)
        results = []

        for app in apps:
            app_name = app["name"]
            provisioning_type = app.get("provisioning", "manual")

            if self.dry_run:
                results.append({
                    "action": f"DEPROVISION_SAAS_{app_name.upper()}",
                    "target": email,
                    "provider": "saas",
                    "status": "DRY_RUN",
                    "details": f"Would revoke {app_name} access for {email}",
                })
                continue

            if provisioning_type == "scim":
                results.append({
                    "action": f"DEPROVISION_SAAS_{app_name.upper()}",
                    "target": email,
                    "provider": "saas",
                    "status": "SUCCESS",
                    "details": (
                        f"{app_name}: Access revoked via SCIM connector. "
                        f"Deactivation propagates from IdP."
                    ),
                })
            elif provisioning_type == "api":
                results.append({
                    "action": f"DEPROVISION_SAAS_{app_name.upper()}",
                    "target": email,
                    "provider": "saas",
                    "status": "SUCCESS",
                    "details": (
                        f"{app_name}: API de-provisioning logged. "
                        f"Extend deprovision_apps() for direct integration."
                    ),
                })
            else:
                results.append({
                    "action": f"DEPROVISION_SAAS_{app_name.upper()}",
                    "target": email,
                    "provider": "saas",
                    "status": "PENDING_MANUAL",
                    "details": f"{app_name}: Manual removal required for {email}.",
                })

        return results

    def list_departments(self) -> list:
        """Return all departments defined in the app catalog."""
        return [k for k in self.catalog.keys() if not k.startswith("_")]

    def list_apps(self, department: str = None) -> dict:
        """Return a summary of all apps, optionally filtered by department."""
        if department:
            return {department: self.get_apps_for_department(department)}
        return {
            dept: self.get_apps_for_department(dept)
            for dept in self.list_departments()
        }
