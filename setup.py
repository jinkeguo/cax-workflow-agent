"""Compatibility entry point for older pip editable-install workflows."""

from setuptools import find_packages, setup


setup(
    name="cax-workflow-agent",
    version="0.1.0",
    description="Bounded MCP adapters for traceable CAD-to-simulation workflows",
    package_dir={"": "mcp"},
    packages=find_packages(where="mcp"),
    package_data={"cae_agent": ["solidworks_bridge.ps1"]},
    install_requires=["pywin32>=306; platform_system == 'Windows'"],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": ["cax-workflow-agent-mcp=cae_agent.mcp_server:main"],
    },
)
