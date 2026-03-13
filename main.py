"""Onboarding Automation Engine - CLI Entry Point.

Orchestrates the full employee onboarding and offboarding workflow:
1. Validate provider and cloud IAM connections
2. Create/deactivate user in identity provider
3. Assign/revoke cloud IAM roles (AWS and/or Azure)
4. Provision/de-provision SaaS applications
5. Log all actions to audit trail

Usage:
    python main.py --mode onboard --provider google --employee "Jane Smith" \
        --email "jane@company.com" --dept Engineering --level L4 --cloud aws

    python main.py --mode offboard --provider google --email "jane@company.com" \
        --dept Engineering --cloud aws

    python main.py --mode bulk-onboard --provider google --file employees.csv \
        --cloud both

    python main.py --mode list-apps --dept Engineering

    Add --dry-run to any command to preview actions without executing them.
"""

import argparse
import csv
import sys

from utils import (
    format_employee_data,
    is_dry_run,
    load_json_config,
    print_banner,
)
from audit_logger import AuditLogger
from saas_provisioner import SaaSProvisioner
from providers.google_workspace import GoogleWorkspaceProvider
from providers.jumpcloud import JumpCloudProvider
from cloud_iam.aws_iam import AWSIAMProvisioner
from cloud_iam.azure_entra import AzureEntraProvisioner


def get_provider(provider_name: str, dry_run: bool):
    """Instantiate the correct identity provider based on name."""
    config = load_json_config("config/provider_config.json")

    providers = {
        "google": lambda: GoogleWorkspaceProvider(
            config.get("google", {}), dry_run=dry_run
        ),
        "jumpcloud": lambda: JumpCloudProvider(
            config.get("jumpcloud", {}), dry_run=dry_run
        ),
    }

    if provider_name not in providers:
        print(f"  [ERROR] Unknown provider: '{provider_name}'")
        print(f"  Available providers: {', '.join(providers.keys())}")
        sys.exit(1)

    return providers[provider_name]()


def get_iam_role_config(department: str, level: str, cloud: str) -> dict:
    """Look up IAM role configuration for a department/level/cloud combination."""
    iam_config = load_json_config("config/iam_roles.json")

    if cloud not in iam_config:
        return iam_config.get(cloud, {}).get("_default", {})

    cloud_config = iam_config[cloud]
    dept_config = cloud_config.get(department, cloud_config.get("_default", {}))

    if isinstance(dept_config, dict) and level in dept_config:
        return dept_config[level]

    return cloud_config.get("_default", {})


def run_onboard(args, audit: AuditLogger):
    """Execute the onboarding workflow for a single employee."""
    dry_run = args.dry_run or is_dry_run()
    provider = get_provider(args.provider, dry_run)
    saas = SaaSProvisioner(dry_run=dry_run)

    employee = format_employee_data(
        name=args.employee,
        email=args.email,
        department=args.dept,
        level=args.level,
        provider=args.provider,
        cloud=args.cloud or "",
    )

    print(f"  Onboarding: {employee['full_name']} ({employee['email']})")
    print(f"  Department: {employee['department']} | Level: {employee['level']}")
    print(f"  Provider: {args.provider} | Cloud: {args.cloud or 'none'}")
    print()

    # Step 1: Validate provider connection
    try:
        provider.validate_connection()
        audit.log(
            "VALIDATE_CONNECTION", args.provider, args.provider, "SUCCESS",
            f"{provider.get_provider_name()} API connection verified"
        )
    except (ConnectionError, Exception) as e:
        audit.log(
            "VALIDATE_CONNECTION", args.provider, args.provider, "FAILED",
            str(e)
        )
        print(f"\n  [ERROR] Provider connection failed. Aborting.\n")
        return False

    # Step 2: Create user in identity provider
    result = provider.create_user(employee)
    status = "DRY_RUN" if dry_run else (
        "SUCCESS" if result["status"] in ("created", "already_exists") else "FAILED"
    )
    audit.log("CREATE_USER", employee["email"], args.provider, status, result["details"])

    if result["status"] == "failed":
        print(f"\n  [ERROR] User creation failed. Aborting.\n")
        return False

    user_id = result.get("user_id", employee["email"])

    # Step 3: Assign to department group in IdP
    dept_group = employee["department"].lower()
    group_ok = provider.assign_to_group(user_id, dept_group)
    audit.log(
        "ASSIGN_IDP_GROUP", f"{employee['email']} -> {dept_group}", args.provider,
        "DRY_RUN" if dry_run else ("SUCCESS" if group_ok else "FAILED"),
        f"{'Assigned' if group_ok else 'Failed to assign'} to IdP group: {dept_group}"
    )

    # Step 4: Cloud IAM provisioning
    clouds = []
    if args.cloud in ("aws", "both"):
        clouds.append("aws")
    if args.cloud in ("azure", "both"):
        clouds.append("azure")

    for cloud in clouds:
        role_config = get_iam_role_config(employee["department"], employee["level"], cloud)

        if cloud == "aws":
            aws = AWSIAMProvisioner(dry_run=dry_run)
            try:
                aws.validate_connection()
                aws_results = aws.provision_user(employee, role_config)
                for r in aws_results:
                    audit.log(
                        r["action"], r["target"], "aws",
                        r["status"], r["details"]
                    )
            except (ConnectionError, Exception) as e:
                audit.log(
                    "AWS_IAM_PROVISION", employee["email"], "aws", "FAILED",
                    f"AWS connection failed: {e}"
                )

        elif cloud == "azure":
            azure = AzureEntraProvisioner(dry_run=dry_run)
            try:
                azure.validate_connection()
                azure_results = azure.provision_user(employee, role_config)
                for r in azure_results:
                    audit.log(
                        r["action"], r["target"], "azure",
                        r["status"], r["details"]
                    )
            except (ConnectionError, Exception) as e:
                audit.log(
                    "AZURE_ENTRA_PROVISION", employee["email"], "azure", "FAILED",
                    f"Azure connection failed: {e}"
                )

    # Step 5: SaaS app provisioning
    saas_results = saas.provision_apps(employee)
    for r in saas_results:
        audit.log(
            r["action"], r["target"], r["provider"],
            r["status"], r["details"]
        )

    return True


def run_offboard(args, audit: AuditLogger):
    """Execute the offboarding workflow for a single employee."""
    dry_run = args.dry_run or is_dry_run()
    provider = get_provider(args.provider, dry_run)
    saas = SaaSProvisioner(dry_run=dry_run)
    department = getattr(args, "dept", None) or "Unknown"

    print(f"  Offboarding: {args.email}")
    print(f"  Provider: {args.provider} | Cloud: {args.cloud or 'none'}")
    print()

    # Step 1: Deactivate in identity provider (revoke access first)
    result = provider.deactivate_user(args.email)
    status_map = {
        "deactivated": "SUCCESS",
        "not_found": "SKIPPED",
        "failed": "FAILED",
        "dry_run": "DRY_RUN",
    }
    audit.log(
        "DEACTIVATE_USER", args.email, args.provider,
        status_map.get(result["status"], "FAILED"), result["details"]
    )

    # Step 2: Cloud IAM de-provisioning
    username = args.email.split("@")[0].replace(".", ".")
    clouds = []
    if args.cloud in ("aws", "both"):
        clouds.append("aws")
    if args.cloud in ("azure", "both"):
        clouds.append("azure")

    for cloud in clouds:
        if cloud == "aws":
            aws = AWSIAMProvisioner(dry_run=dry_run)
            try:
                aws_results = aws.deprovision_user(username)
                for r in aws_results:
                    audit.log(r["action"], r["target"], "aws", r["status"], r["details"])
            except Exception as e:
                audit.log(
                    "AWS_IAM_DEPROVISION", args.email, "aws", "FAILED",
                    f"AWS de-provisioning failed: {e}"
                )

        elif cloud == "azure":
            azure = AzureEntraProvisioner(dry_run=dry_run)
            try:
                azure_results = azure.deprovision_user(args.email)
                for r in azure_results:
                    audit.log(r["action"], r["target"], "azure", r["status"], r["details"])
            except Exception as e:
                audit.log(
                    "AZURE_ENTRA_DEPROVISION", args.email, "azure", "FAILED",
                    f"Azure de-provisioning failed: {e}"
                )

    # Step 3: SaaS app de-provisioning
    saas_results = saas.deprovision_apps(args.email, department)
    for r in saas_results:
        audit.log(r["action"], r["target"], r["provider"], r["status"], r["details"])

    return True


def run_bulk_onboard(args, audit: AuditLogger):
    """Onboard multiple employees from a CSV file."""
    if not args.file:
        print("  [ERROR] --file is required for bulk-onboard mode.")
        sys.exit(1)

    try:
        with open(args.file, "r") as f:
            reader = csv.DictReader(f)
            employees = list(reader)
    except FileNotFoundError:
        print(f"  [ERROR] File not found: {args.file}")
        sys.exit(1)

    print(f"  Bulk onboarding {len(employees)} employees from {args.file}")
    print()

    success_count = 0
    fail_count = 0

    for emp in employees:
        # Build a namespace object that matches single onboard args
        onboard_args = argparse.Namespace(
            mode="onboard",
            provider=args.provider,
            employee=emp.get("full_name", ""),
            email=emp.get("email", ""),
            dept=emp.get("department", ""),
            level=emp.get("level", "L1"),
            cloud=args.cloud or "",
            dry_run=args.dry_run,
        )

        print(f"  {'=' * 50}")
        ok = run_onboard(onboard_args, audit)
        if ok:
            success_count += 1
        else:
            fail_count += 1
        print()

    print(f"  Bulk onboard complete: {success_count} succeeded, {fail_count} failed")
    return fail_count == 0


def run_list_apps(args):
    """List all configured SaaS apps, optionally filtered by department."""
    saas = SaaSProvisioner()
    department = getattr(args, "dept", None)
    apps = saas.list_apps(department)

    for dept, app_list in apps.items():
        print(f"\n  {dept}:")
        for app in app_list:
            prov_type = app.get("provisioning", "manual")
            role = app.get("default_role", "member")
            print(f"    - {app['name']:15s} ({prov_type:6s})  default role: {role}")
    print()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Onboarding Automation Engine - Employee lifecycle management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode onboard --provider google --employee "Jane Smith" \\
      --email "jane@co.com" --dept Engineering --level L4 --cloud aws

  python main.py --mode offboard --provider jumpcloud \\
      --email "jane@co.com" --dept Engineering --cloud both

  python main.py --mode bulk-onboard --provider google \\
      --file employees.csv --cloud both

  python main.py --mode list-apps --dept Engineering

  Add --dry-run to preview without executing.
        """,
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=["onboard", "offboard", "bulk-onboard", "list-apps"],
        help="Operation mode",
    )
    parser.add_argument(
        "--provider",
        choices=["google", "jumpcloud"],
        help="Identity provider to use",
    )
    parser.add_argument("--employee", help="Employee full name (for onboard)")
    parser.add_argument("--email", help="Employee email address")
    parser.add_argument("--dept", help="Department name (must match app_catalog.json)")
    parser.add_argument(
        "--level", default="L1", help="Job level (e.g., L1-L5). Default: L1"
    )
    parser.add_argument(
        "--cloud",
        choices=["aws", "azure", "both", "none"],
        default="none",
        help="Cloud IAM platform(s) to provision. Default: none",
    )
    parser.add_argument("--file", help="CSV file path for bulk-onboard mode")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview all actions without executing them",
    )

    return parser


def validate_args(args):
    """Validate argument combinations for the selected mode."""
    if args.mode == "onboard":
        missing = []
        if not args.provider:
            missing.append("--provider")
        if not args.employee:
            missing.append("--employee")
        if not args.email:
            missing.append("--email")
        if not args.dept:
            missing.append("--dept")
        if missing:
            print(f"  [ERROR] Missing required arguments for onboard: {', '.join(missing)}")
            sys.exit(1)

    elif args.mode == "offboard":
        missing = []
        if not args.provider:
            missing.append("--provider")
        if not args.email:
            missing.append("--email")
        if missing:
            print(f"  [ERROR] Missing required arguments for offboard: {', '.join(missing)}")
            sys.exit(1)

    elif args.mode == "bulk-onboard":
        if not args.provider:
            print("  [ERROR] --provider is required for bulk-onboard mode.")
            sys.exit(1)
        if not args.file:
            print("  [ERROR] --file is required for bulk-onboard mode.")
            sys.exit(1)


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Handle list-apps separately (no audit needed)
    if args.mode == "list-apps":
        print_banner("list-apps")
        run_list_apps(args)
        return

    validate_args(args)

    # Override dry_run from environment if flag not set
    if not args.dry_run and is_dry_run():
        args.dry_run = True

    print_banner(args.mode)
    audit = AuditLogger()

    mode_handlers = {
        "onboard": run_onboard,
        "offboard": run_offboard,
        "bulk-onboard": run_bulk_onboard,
    }

    handler = mode_handlers[args.mode]
    success = handler(args, audit)

    audit.print_summary()

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
