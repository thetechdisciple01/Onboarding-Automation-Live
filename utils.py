"""Shared utility functions for the onboarding automation engine."""

import os
import json
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, required: bool = True) -> str:
    """Retrieve environment variable with validation."""
    value = os.getenv(key, "")
    if required and not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Check your .env file or environment configuration."
        )
    return value


def is_dry_run() -> bool:
    """Check if the engine is running in dry-run mode."""
    return os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")


def load_json_config(filepath: str) -> dict:
    """Load and return a JSON configuration file."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filepath)
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, "r") as f:
        return json.load(f)


def generate_username(full_name: str, domain: str = "") -> str:
    """Generate a username from a full name.

    Args:
        full_name: Employee's full name (e.g., 'Jane Smith')
        domain: Optional email domain (e.g., 'company.com')

    Returns:
        Username string (e.g., 'jane.smith' or 'jane.smith@company.com')
    """
    parts = full_name.strip().lower().split()
    if len(parts) < 2:
        raise ValueError(f"Full name must include first and last name: '{full_name}'")
    username = f"{parts[0]}.{parts[-1]}"
    username = re.sub(r"[^a-z0-9.]", "", username)
    if domain:
        return f"{username}@{domain}"
    return username


def generate_temp_password(length: int = 16) -> str:
    """Generate a temporary password for new accounts.

    Uses secrets module for cryptographic randomness.
    """
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%&*" for c in password)
        if has_upper and has_lower and has_digit and has_special:
            return password


def timestamp_now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def format_employee_data(
    name: str, email: str, department: str, level: str, provider: str, cloud: str = ""
) -> dict:
    """Build a standardized employee data dictionary."""
    return {
        "full_name": name.strip(),
        "email": email.strip().lower(),
        "department": department.strip(),
        "level": level.strip().upper(),
        "provider": provider.strip().lower(),
        "cloud": cloud.strip().lower() if cloud else "",
        "username": generate_username(name),
        "created_at": timestamp_now(),
    }


def print_banner(mode: str):
    """Print a startup banner for CLI output."""
    bar = "=" * 56
    print(f"\n{bar}")
    print(f"  Onboarding Automation Engine")
    print(f"  Mode: {mode.upper()}")
    print(f"  Dry Run: {'YES' if is_dry_run() else 'NO'}")
    print(f"  Timestamp: {timestamp_now()}")
    print(f"{bar}\n")
