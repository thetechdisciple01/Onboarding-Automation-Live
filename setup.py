"""Setup configuration for the Onboarding Automation Engine."""

from setuptools import setup, find_packages

setup(
    name="onboarding-automation",
    version="1.0.0",
    description=(
        "A lightweight, production-ready employee onboarding and offboarding engine "
        "for startups. Integrates with Google Workspace, JumpCloud, AWS IAM, and "
        "Azure Entra ID with config-driven SaaS app provisioning."
    ),
    author="Bricesen Ross",
    author_email="bricesen@thetechdisciple.com",
    url="https://github.com/thetechdisciple01/onboarding-automation-live",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "google-api-python-client>=2.100.0",
        "google-auth>=2.23.0",
        "google-auth-httplib2>=0.1.1",
        "google-auth-oauthlib>=1.1.0",
        "boto3>=1.29.0",
        "azure-identity>=1.15.0",
        "requests>=2.31.0",
        "pandas>=2.1.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "onboard=main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Systems Administration",
    ],
)
