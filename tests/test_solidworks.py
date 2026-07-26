from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cae_agent.solidworks import (
    _candidate_executables,
    _invoke_bridge,
    export_solidworks_document,
    get_solidworks_environment,
    instantiate_solidworks_template,
    test_solidworks_connection,
)


class SolidWorksAdapterTests(unittest.TestCase):
    def test_environment_query_is_non_mutating(self):
        result = get_solidworks_environment()
        self.assertEqual(result.status, "succeeded")
        self.assertIn("runtime_available", result.checks)
        self.assertEqual(result.checks["com_progid"], "SldWorks.Application")
        self.assertIn("bridge_backend", result.checks)

    @patch("cae_agent.solidworks._registered_executable")
    def test_registered_custom_install_path_is_a_candidate(self, registered):
        registered.return_value = Path(r"D:\Custom SolidWorks\SLDWORKS.exe")
        candidates = _candidate_executables()
        self.assertIn(registered.return_value.resolve(), candidates)

    @patch("cae_agent.solidworks._runtime_gate", return_value=None)
    @patch("cae_agent.solidworks._invoke_bridge")
    def test_connection_smoke_returns_revision(self, bridge, _runtime_gate):
        bridge.return_value = (
            {
                "status": "succeeded",
                "checks": {
                    "connection": "ok",
                    "com_backend": "pywin32-dynamic-idispatch",
                },
                "warnings": [],
                "solidworks_revision": "33.5.1",
            },
            Path(tempfile.gettempdir()),
            [],
        )
        result = test_solidworks_connection()
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.application["version"], "33.5.1")
        self.assertEqual(result.checks["connection"], "ok")

    def test_template_preview_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / "template.sldprt"
            output = Path(directory) / "output.sldprt"
            export = Path(directory) / "output.step"
            template.write_bytes(b"mock-solidworks-template")
            result = instantiate_solidworks_template(
                str(template),
                str(output),
                {"D1@Sketch1": 100.0, "D1@Boss-Extrude1": 2.0},
                export_path=str(export),
            )
            self.assertEqual(result.status, "needs_input")
            self.assertFalse(output.exists())
            self.assertFalse(export.exists())
            self.assertIn("write_preview", result.checks)

    def test_export_preview_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sldprt"
            target = Path(directory) / "source.x_t"
            source.write_bytes(b"mock-solidworks-part")
            result = export_solidworks_document(str(source), str(target))
            self.assertEqual(result.status, "needs_input")
            self.assertFalse(target.exists())

    @patch("cae_agent.solidworks._runtime_gate", return_value=None)
    @patch("cae_agent.solidworks._invoke_bridge")
    def test_template_commit_uses_staging_and_preserves_template(
        self, bridge, _runtime_gate
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.sldprt"
            output = root / "generated.sldprt"
            export = root / "generated.step"
            original = b"template-content"
            template.write_bytes(original)

            def fake_bridge(request, timeout_seconds):
                Path(request["input_path"]).write_bytes(b"parameterized-content")
                Path(request["export_path"]).write_bytes(b"step-content")
                return (
                    {
                        "status": "succeeded",
                        "checks": {
                            "dimension_changes": [
                                {"name": "D1@Sketch1", "old_mm": 10.0, "new_mm": 100.0}
                            ],
                            "rebuilt": True,
                        },
                        "warnings": [],
                        "solidworks_revision": "mock",
                    },
                    root,
                    [],
                )

            bridge.side_effect = fake_bridge
            result = instantiate_solidworks_template(
                str(template),
                str(output),
                {"D1@Sketch1": 100.0},
                export_path=str(export),
                confirm_write=True,
            )
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(template.read_bytes(), original)
            self.assertEqual(output.read_bytes(), b"parameterized-content")
            self.assertEqual(export.read_bytes(), b"step-content")

    def test_powershell_bridge_returns_structured_failure_without_solidworks(self):
        if get_solidworks_environment().checks["runtime_available"]:
            self.skipTest("This regression is for hosts without SolidWorks COM")
        response, _, _ = _invoke_bridge(
            {
                "operation": "inspect",
                "input_path": r"C:\nonexistent\model.sldprt",
                "dimension_names": [],
                "visible": False,
            },
            30,
        )
        self.assertEqual(response["status"], "failed")
        self.assertTrue(response["error"])


if __name__ == "__main__":
    unittest.main()
