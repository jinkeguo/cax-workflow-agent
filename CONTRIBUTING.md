# Contributing to CAX Workflow Agent

Contributions should preserve the project's core boundary: adapters expose
small, reviewable operations and return evidence rather than claiming success
from a process exit code alone.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
$env:PYTHONPATH = "$PWD\mcp"
python -m unittest discover -s tests -v
```

## Pull requests

1. Keep each adapter operation bounded and deterministic.
2. Add a portable unit test for new behavior.
3. Put application-dependent tests behind explicit environment checks.
4. Preserve preview-before-write and no-overwrite defaults.
5. Document any new environment variable or artifact type.
6. Do not include proprietary models, solver outputs, license data, user paths,
   hostnames, or credentials.

Commit messages should describe the engineering boundary changed, for example:
`feat(solidworks): inspect named template dimensions`.

## Commercial application tests

Live tests must use disposable copies and isolated run directories. Never mutate
the source template. A contributor running licensed software is responsible for
complying with the vendor license and local security policy.
