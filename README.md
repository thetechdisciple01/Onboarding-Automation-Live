# Startup Onboarding Automation Engine

## A lightweight, production-ready alternative to enterprise onboarding tools

Built for early and mid-stage startups that need structured employee onboarding and offboarding without the cost of enterprise platforms like Okta, Rippling, or JumpCloud's paid tiers.

## What This Does

This tool automates the full employee lifecycle (onboarding and offboarding) by integrating directly with the platforms your startup already uses:

- **Identity Providers**: Google Workspace, JumpCloud (free tier), or bring your own
- **Cloud IAM**: AWS IAM and/or Azure Entra ID role assignment
- **SaaS Apps**: Config-driven, define your own app catalog (Slack, Notion, GitHub, Jira, Linear, Figma, etc.)
- **Audit Trail**: Every provisioning and de-provisioning action logged to CSV with timestamps

## Why This Exists

Enterprise onboarding tools cost $8-15/user/month and require contracts most startups can't justify at 10-50 employees. But manual onboarding is a security risk and an operational drag. New hires waiting days for access, orphaned accounts after departures, zero audit trail.

This engine gives you enterprise-grade onboarding discipline at zero licensing cost. You bring your own API keys, you own your data, you control the workflow.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  main.py (CLI)                   │
│         --mode onboard | offboard                │
│         --provider google | jumpcloud            │
├─────────────────────────────────────────────────┤
│              Provider Router                     │
│    Routes to the correct IdP integration         │
├──────────┬──────────┬───────────────────────────┤
│  Google  │JumpCloud │   Custom Provider         │
│Workspace │  (Free)  │   (Extensible)            │
├──────────┴──────────┴───────────────────────────┤
│              SaaS App Provisioner                │
│    Config-driven app assignment by department    │
├──────────┬──────────────────────────────────────┤
│  AWS IAM │  Azure Entra ID                      │
│  Roles   │  Role Assignment                     │
├──────────┴──────────────────────────────────────┤
│              Audit Logger                        │
│    CSV + console logging for all actions         │
└─────────────────────────────────────────────────┘
```

## Supported Providers

| Provider | Auth Method | What It Provisions |
|----------|------------|-------------------|
| Google Workspace | Service Account (OAuth2) | User creation, Org Unit, Group membership, App licensing |
| JumpCloud | API Key | User creation, Group binding, System association |
| AWS IAM | Access Key / Role | IAM user, group membership, policy attachment |
| Azure Entra ID | Service Principal (OAuth2) | User creation, group membership, role assignment |

## Project Structure

```
onboarding-automation-live/
├── README.md
├── requirements.txt
├── setup.py
├── .env.example
├── config/
│   ├── app_catalog.json          # Define your SaaS stack by department
│   ├── iam_roles.json            # AWS/Azure role mappings by level
│   └── provider_config.json      # Provider-specific settings
├── providers/
│   ├── __init__.py
│   ├── base_provider.py          # Abstract base class
│   ├── google_workspace.py       # Google Workspace Admin SDK
│   ├── jumpcloud.py              # JumpCloud Directory API
│   └── custom_provider.py        # Template for custom integrations
├── cloud_iam/
│   ├── __init__.py
│   ├── aws_iam.py                # Live AWS IAM provisioning
│   └── azure_entra.py            # Azure Entra ID provisioning
├── saas_provisioner.py           # Config-driven SaaS app assignment
├── audit_logger.py               # Audit trail and reporting
├── main.py                       # CLI entry point
├── utils.py                      # Shared utilities
└── tests/
    ├── __init__.py
    ├── test_google_workspace.py
    ├── test_jumpcloud.py
    ├── test_aws_iam.py
    ├── test_azure_entra.py
    ├── test_saas_provisioner.py
    └── test_main.py
```

## Setup & Installation

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/onboarding-automation-live.git
cd onboarding-automation-live
pip install -r requirements.txt
```

### 2. Configure your environment

```bash
cp .env.example .env
# Edit .env with your API keys and credentials
```

### 3. Define your app catalog

Edit `config/app_catalog.json` to match your startup's SaaS stack:

```json
{
  "Engineering": {
    "apps": ["github", "jira", "slack", "notion", "datadog"],
    "default_role": "member"
  },
  "Design": {
    "apps": ["figma", "slack", "notion", "miro"],
    "default_role": "member"
  }
}
```

### 4. Run onboarding

```bash
# Onboard with Google Workspace as IdP
python main.py --mode onboard \
  --provider google \
  --employee "Jane Smith" \
  --email "jane.smith@company.com" \
  --dept Engineering \
  --level L4 \
  --cloud aws

# Onboard with JumpCloud
python main.py --mode onboard \
  --provider jumpcloud \
  --employee "Marcus Johnson" \
  --email "marcus@company.com" \
  --dept Design \
  --level L3 \
  --cloud azure

# Offboard (works with any provider)
python main.py --mode offboard \
  --provider google \
  --email "jane.smith@company.com"

# Bulk onboard from CSV
python main.py --mode bulk-onboard \
  --provider google \
  --file employees.csv \
  --cloud both
```

## Configuration Reference

### Provider Config (`config/provider_config.json`)

```json
{
  "google": {
    "domain": "yourcompany.com",
    "admin_email": "admin@yourcompany.com",
    "credentials_file": "service_account.json",
    "default_org_unit": "/Employees"
  },
  "jumpcloud": {
    "org_id": "your_jumpcloud_org_id"
  }
}
```

### IAM Role Mapping (`config/iam_roles.json`)

```json
{
  "aws": {
    "Engineering": {
      "L3": ["AmazonEC2ReadOnlyAccess", "AmazonS3ReadOnlyAccess"],
      "L4": ["PowerUserAccess"],
      "L5": ["PowerUserAccess", "IAMFullAccess"]
    }
  },
  "azure": {
    "Engineering": {
      "L3": ["Reader"],
      "L4": ["Contributor"],
      "L5": ["Owner"]
    }
  }
}
```

## Adding a Custom Provider

Extend the `BaseProvider` class:

```python
from providers.base_provider import BaseProvider

class YourProvider(BaseProvider):
    def create_user(self, employee_data: dict) -> dict:
        # Your provisioning logic
        pass

    def assign_to_group(self, user_id: str, group: str) -> bool:
        # Group assignment logic
        pass

    def deactivate_user(self, user_id: str) -> bool:
        # De-provisioning logic
        pass
```

## Security Notes

- API keys and secrets are loaded from environment variables (never hardcoded)
- All provisioning actions are logged with timestamps and actor context
- Offboarding revokes all access before deactivating accounts (revoke-first pattern)
- Supports dry-run mode (`--dry-run`) to preview changes before execution

## Who This Is For

- **Early-stage startups** (5-50 employees) that need onboarding structure without enterprise contracts
- **IT leads at growing companies** building operational discipline before scaling
- **Solo IT operators** managing a growing SaaS stack manually
- **Anyone** who has onboarded a new hire by copying someone else's app list from a sticky note

## License

MIT
