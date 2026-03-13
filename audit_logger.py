"""Audit logger for tracking all provisioning and de-provisioning actions.

Every action taken by the onboarding engine is recorded with:
- Timestamp (UTC)
- Action type (CREATE_USER, ASSIGN_GROUP, ATTACH_POLICY, etc.)
- Target (the user or resource being acted on)
- Provider (google, jumpcloud, aws, azure)
- Status (SUCCESS, FAILED, DRY_RUN, SKIPPED)
- Details (human-readable context)
"""

import csv
import os
from datetime import datetime, timezone
from utils import get_env


class AuditLogger:
    """Handles audit trail logging to CSV and console."""

    VALID_STATUSES = {"SUCCESS", "FAILED", "DRY_RUN", "SKIPPED", "PENDING_MANUAL"}

    def __init__(self, log_path: str = None):
        self.log_path = log_path or get_env("AUDIT_LOG_PATH", required=False) or "audit_log.csv"
        self.entries = []
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Create the CSV file with headers if it does not exist."""
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "action",
                    "target",
                    "provider",
                    "status",
                    "details",
                ])

    def log(
        self,
        action: str,
        target: str,
        provider: str,
        status: str,
        details: str = "",
    ):
        """Record a single audit entry.

        Args:
            action: Action type (e.g., CREATE_USER, ASSIGN_GROUP)
            target: The user or resource (e.g., jane.smith@company.com)
            provider: Integration name (google, jumpcloud, aws, azure, saas)
            status: Outcome status (SUCCESS, FAILED, DRY_RUN, SKIPPED, PENDING_MANUAL)
            details: Optional human-readable context
        """
        if status not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {self.VALID_STATUSES}"
            )

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "target": target,
            "provider": provider,
            "status": status,
            "details": details,
        }

        self.entries.append(entry)
        self._write_entry(entry)
        self._print_entry(entry)

    def _write_entry(self, entry: dict):
        """Append a single entry to the CSV log."""
        with open(self.log_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                entry["timestamp"],
                entry["action"],
                entry["target"],
                entry["provider"],
                entry["status"],
                entry["details"],
            ])

    def _print_entry(self, entry: dict):
        """Print a formatted entry to the console."""
        status_icons = {
            "SUCCESS": "[OK]",
            "FAILED": "[FAIL]",
            "DRY_RUN": "[DRY]",
            "SKIPPED": "[SKIP]",
            "PENDING_MANUAL": "[TODO]",
        }
        icon = status_icons.get(entry["status"], "[??]")
        print(
            f"  {icon} {entry['action']:25s} | "
            f"{entry['provider']:12s} | "
            f"{entry['target']:35s} | "
            f"{entry['details']}"
        )

    def get_summary(self) -> dict:
        """Return a summary of all logged actions."""
        summary = {
            "total_actions": len(self.entries),
            "successful": sum(1 for e in self.entries if e["status"] == "SUCCESS"),
            "failed": sum(1 for e in self.entries if e["status"] == "FAILED"),
            "dry_run": sum(1 for e in self.entries if e["status"] == "DRY_RUN"),
            "pending_manual": sum(1 for e in self.entries if e["status"] == "PENDING_MANUAL"),
            "skipped": sum(1 for e in self.entries if e["status"] == "SKIPPED"),
        }
        return summary

    def print_summary(self):
        """Print a formatted summary to the console."""
        summary = self.get_summary()
        bar = "-" * 45
        print(f"\n{bar}")
        print("  AUDIT SUMMARY")
        print(f"{bar}")
        print(f"  Total Actions:    {summary['total_actions']}")
        print(f"  Successful:       {summary['successful']}")
        print(f"  Failed:           {summary['failed']}")
        print(f"  Dry Run:          {summary['dry_run']}")
        print(f"  Pending Manual:   {summary['pending_manual']}")
        print(f"  Skipped:          {summary['skipped']}")
        print(f"{bar}")
        print(f"  Audit log saved to: {self.log_path}\n")
