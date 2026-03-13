"""Tests for the config-driven SaaS provisioner."""

import unittest
import json
import tempfile
import os
from saas_provisioner import SaaSProvisioner


class TestSaaSProvisioner(unittest.TestCase):
    """Test SaaS provisioner with a temporary app catalog."""

    def setUp(self):
        self.test_catalog = {
            "Engineering": {
                "apps": [
                    {"name": "github", "provisioning": "api", "default_role": "member"},
                    {"name": "slack", "provisioning": "scim", "default_role": "member"},
                    {"name": "datadog", "provisioning": "manual", "default_role": "standard"},
                ]
            },
            "Design": {
                "apps": [
                    {"name": "figma", "provisioning": "scim", "default_role": "editor"},
                ]
            },
        }

        # Write catalog to a temp file
        self.temp_dir = tempfile.mkdtemp()
        self.catalog_path = os.path.join(self.temp_dir, "app_catalog.json")
        with open(self.catalog_path, "w") as f:
            json.dump(self.test_catalog, f)

        self.employee = {
            "full_name": "Jane Smith",
            "email": "jane.smith@testcompany.com",
            "department": "Engineering",
            "level": "L4",
            "username": "jane.smith",
        }

    def test_get_apps_for_department(self):
        saas = SaaSProvisioner(catalog_path=self.catalog_path)
        apps = saas.get_apps_for_department("Engineering")
        self.assertEqual(len(apps), 3)
        app_names = [a["name"] for a in apps]
        self.assertIn("github", app_names)
        self.assertIn("slack", app_names)
        self.assertIn("datadog", app_names)

    def test_get_apps_unknown_department(self):
        saas = SaaSProvisioner(catalog_path=self.catalog_path)
        apps = saas.get_apps_for_department("NonExistent")
        self.assertEqual(len(apps), 0)

    def test_provision_apps_dry_run(self):
        saas = SaaSProvisioner(catalog_path=self.catalog_path, dry_run=True)
        results = saas.provision_apps(self.employee)
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertEqual(r["status"], "DRY_RUN")

    def test_provision_apps_live(self):
        saas = SaaSProvisioner(catalog_path=self.catalog_path, dry_run=False)
        results = saas.provision_apps(self.employee)
        self.assertEqual(len(results), 3)

        # Check provisioning types produce correct statuses
        status_by_app = {r["action"].split("_")[-1].lower(): r["status"] for r in results}
        self.assertEqual(status_by_app.get("github"), "SUCCESS")  # api
        self.assertEqual(status_by_app.get("slack"), "SUCCESS")  # scim
        self.assertEqual(status_by_app.get("datadog"), "PENDING_MANUAL")  # manual

    def test_deprovision_apps(self):
        saas = SaaSProvisioner(catalog_path=self.catalog_path, dry_run=False)
        results = saas.deprovision_apps("jane.smith@testcompany.com", "Engineering")
        self.assertEqual(len(results), 3)

    def test_list_departments(self):
        saas = SaaSProvisioner(catalog_path=self.catalog_path)
        depts = saas.list_departments()
        self.assertIn("Engineering", depts)
        self.assertIn("Design", depts)

    def test_list_apps_all(self):
        saas = SaaSProvisioner(catalog_path=self.catalog_path)
        all_apps = saas.list_apps()
        self.assertIn("Engineering", all_apps)
        self.assertIn("Design", all_apps)

    def test_list_apps_filtered(self):
        saas = SaaSProvisioner(catalog_path=self.catalog_path)
        filtered = saas.list_apps("Design")
        self.assertIn("Design", filtered)
        self.assertNotIn("Engineering", filtered)


if __name__ == "__main__":
    unittest.main()
