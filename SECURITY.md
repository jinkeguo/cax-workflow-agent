# Security policy

## Reporting

Do not open a public issue for a vulnerability, credential exposure, unsafe file
overwrite, or unintended commercial-application action. Until a private
security contact is configured for the GitHub repository, contact the repository
owner privately through their GitHub profile.

## Sensitive engineering data

CAX Workflow Agent may process proprietary CAD, mesh, input-deck, job, and result files.
Keep those artifacts outside the repository. Before sharing logs, inspect them
for usernames, absolute paths, hostnames, license-server addresses, model names,
and customer data.

## Execution boundary

The plugin launches locally installed commercial applications. Review adapter
changes carefully. Native-file writes must remain staged, existing outputs must
not be overwritten by default, and expensive solver submission must require an
explicit approval boundary.
