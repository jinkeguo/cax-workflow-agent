from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cae_agent.diagnostics import diagnose_cae_failure


class DiagnosticTests(unittest.TestCase):
    def test_abaqus_wmi_and_datacheck_failure(self):
        result = diagnose_cae_failure(
            log_text=(
                "getWMI: Query for operating system name failed.\n"
                "Abaqus Error: The number of cpus (1) exceeds the number "
                "of cpus available (-1).\n"
                "Abaqus/Datacheck exited with error(s).\n"
            )
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.checks["detected_application"], "abaqus")
        codes = {item["code"] for item in result.checks["matched_issues"]}
        self.assertIn("abq-wmi-cpu-query", codes)
        self.assertIn("abq-datacheck-error", codes)
        self.assertTrue(
            any(
                item["recommended_tool"] == "run_abaqus_datacheck"
                for item in result.checks["matched_issues"]
            )
        )

    def test_abaqus_compact_wmi_signature(self):
        result = diagnose_cae_failure(
            application="auto",
            stage="abaqus_datacheck",
            log_text=(
                "getWMI... available (-1)\n"
                "Abaqus/Datacheck exited with error(s)."
            ),
        )
        codes = {item["code"] for item in result.checks["matched_issues"]}
        self.assertEqual(result.checks["detected_application"], "abaqus")
        self.assertIn("abq-wmi-cpu-query", codes)
        self.assertIn("abq-datacheck-error", codes)

    def test_hypermesh_newmodel_failure(self):
        result = diagnose_cae_failure(
            application="hypermesh",
            log_text='invalid command name "*newmodel"',
        )
        self.assertEqual(result.status, "succeeded")
        issue = result.checks["matched_issues"][0]
        self.assertEqual(issue["code"], "hm-invalid-newmodel")
        self.assertEqual(issue["recovery"], "automatic")

    def test_solidworks_dimension_guidance(self):
        result = diagnose_cae_failure(
            application="solidworks",
            log_text="Dimension D1@RepairSketch not found; Parameter returned null",
        )
        self.assertEqual(result.status, "succeeded")
        issue = result.checks["matched_issues"][0]
        self.assertEqual(issue["code"], "sw-dimension-not-found")
        self.assertEqual(issue["recommended_tool"], "inspect_solidworks_document")

    def test_log_path_and_unknown_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown.log"
            path.write_text("vendor-specific unexplained failure 9917\n", encoding="utf-8")
            result = diagnose_cae_failure(log_path=str(path))
        self.assertEqual(result.status, "needs_input")
        self.assertEqual(result.checks["match_count"], 0)
        self.assertTrue(result.artifacts)
        self.assertTrue(result.warnings)

    def test_requires_evidence(self):
        result = diagnose_cae_failure()
        self.assertEqual(result.status, "needs_input")


if __name__ == "__main__":
    unittest.main()
