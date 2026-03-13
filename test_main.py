"""Tests for the CLI entry point and utility functions."""

import unittest
import os
import tempfile
from unittest.mock import patch
from utils import generate_username, generate_temp_password, format_employee_data
from audit_logger import AuditLogger


class TestUtils(unittest.TestCase):
    """Test utility functions."""

    def test_generate_username_basic(self):
        self.assertEqual(generate_username("Jane Smith"), "jane.smith")

    def test_generate_username_with_domain(self):
        result = generate_username("Jane Smith", "company.com")
        self.assertEqual(result, "jane.smith@company.com")

    def test_generate_username_multi_word_last(self):
        result = generate_username("Mary Jane Watson")
        self.assertEqual(result, "mary.watson")

    def test_generate_username_strips_special(self):
        result = generate_username("Jane O'Smith")
        self.assertEqual(result, "jane.osmith")

    def test_generate_username_single_name_fails(self):
        with self.assertRaises(ValueError):
            generate_username("Jane")

    def test_generate_temp_password_length(self):
        pw = generate_temp_password(20)
        self.assertEqual(len(pw), 20)

    def test_generate_temp_password_complexity(self):
        pw = generate_temp_password()
        self.assertTrue(any(c.isupper() for c in pw))
        self.assertTrue(any(c.islower() for c in pw))
        self.assertTrue(any(c.isdigit() for c in pw))

    def test_format_employee_data(self):
        data = format_employee_data(
            name="Jane Smith",
            email="jane@co.com",
            department="Engineering",
            level="L4",
            provider="google",
            cloud="aws",
        )
        self.assertEqual(data["full_name"], "Jane Smith")
        self.assertEqual(data["email"], "jane@co.com")
        self.assertEqual(data["username"], "jane.smith")
        self.assertEqual(data["level"], "L4")
        self.assertIn("created_at", data)


class TestAuditLogger(unittest.TestCase):
    """Test audit logging functionality."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        )
        self.temp_file.close()
        self.logger = AuditLogger(log_path=self.temp_file.name)

    def tearDown(self):
        os.unlink(self.temp_file.name)

    def test_log_entry(self):
        self.logger.log(
            "CREATE_USER", "jane@co.com", "google", "SUCCESS", "Test entry"
        )
        self.assertEqual(len(self.logger.entries), 1)
        self.assertEqual(self.logger.entries[0]["action"], "CREATE_USER")

    def test_log_invalid_status(self):
        with self.assertRaises(ValueError):
            self.logger.log(
                "CREATE_USER", "jane@co.com", "google", "INVALID", "Bad status"
            )

    def test_summary(self):
        self.logger.log("A", "t", "p", "SUCCESS", "")
        self.logger.log("B", "t", "p", "FAILED", "")
        self.logger.log("C", "t", "p", "DRY_RUN", "")
        self.logger.log("D", "t", "p", "PENDING_MANUAL", "")

        summary = self.logger.get_summary()
        self.assertEqual(summary["total_actions"], 4)
        self.assertEqual(summary["successful"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["dry_run"], 1)
        self.assertEqual(summary["pending_manual"], 1)

    def test_csv_persistence(self):
        self.logger.log("TEST", "target", "provider", "SUCCESS", "persist check")
        with open(self.temp_file.name, "r") as f:
            content = f.read()
        self.assertIn("TEST", content)
        self.assertIn("persist check", content)


class TestMainCLI(unittest.TestCase):
    """Test CLI argument parsing and validation."""

    def test_import_main(self):
        """Verify main module imports without errors."""
        import main
        self.assertTrue(hasattr(main, "main"))
        self.assertTrue(hasattr(main, "build_parser"))

    def test_parser_onboard_args(self):
        from main import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--mode", "onboard",
            "--provider", "google",
            "--employee", "Jane Smith",
            "--email", "jane@co.com",
            "--dept", "Engineering",
            "--level", "L4",
            "--cloud", "aws",
            "--dry-run",
        ])
        self.assertEqual(args.mode, "onboard")
        self.assertEqual(args.provider, "google")
        self.assertEqual(args.employee, "Jane Smith")
        self.assertTrue(args.dry_run)

    def test_parser_offboard_args(self):
        from main import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--mode", "offboard",
            "--provider", "jumpcloud",
            "--email", "jane@co.com",
            "--cloud", "both",
        ])
        self.assertEqual(args.mode, "offboard")
        self.assertEqual(args.cloud, "both")

    def test_parser_bulk_args(self):
        from main import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--mode", "bulk-onboard",
            "--provider", "google",
            "--file", "employees.csv",
            "--cloud", "both",
        ])
        self.assertEqual(args.mode, "bulk-onboard")
        self.assertEqual(args.file, "employees.csv")

    def test_parser_list_apps(self):
        from main import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--mode", "list-apps",
            "--dept", "Engineering",
        ])
        self.assertEqual(args.mode, "list-apps")
        self.assertEqual(args.dept, "Engineering")


if __name__ == "__main__":
    unittest.main()
