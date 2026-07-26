from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cae_agent.abaqus_runtime import (
    cancel_abaqus_job,
    inspect_abaqus_job,
    retry_abaqus_job,
    run_abaqus_datacheck,
    submit_abaqus_job,
)


class AbaqusRuntimeTests(unittest.TestCase):
    def test_submit_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "model.inp"
            deck.write_text("*HEADING\n", encoding="utf-8")
            result = submit_abaqus_job(
                str(deck), str(root / "run"), "safe_preview"
            )
        self.assertEqual(result.status, "needs_confirmation")
        self.assertEqual(result.checks["operation"], "submit_abaqus_analysis")

    def test_cancel_requires_running_job_and_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "running_job.lck").write_text("", encoding="utf-8")
            result = cancel_abaqus_job(str(root), "running_job")
        self.assertEqual(result.status, "needs_confirmation")
        self.assertEqual(result.checks["job_state"], "running")

    def test_retry_rejects_model_failure_without_reviewed_deck(self):
        with tempfile.TemporaryDirectory() as directory:
            result = retry_abaqus_job(
                directory,
                "failed_job",
                "retry_job",
                "convergence-failure",
            )
        self.assertEqual(result.status, "needs_input")
        self.assertIn("reviewed new deck", result.error)

    def test_inspect_completed_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "portable_job.sta").write_text(
                "THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n", encoding="utf-8"
            )
            (root / "portable_job.odb").write_bytes(b"portable-test-placeholder")
            result = inspect_abaqus_job(str(root), "portable_job")
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.checks["job_state"], "completed")
            self.assertTrue(result.checks["odb_exists"])

    def test_datacheck_rejects_includes_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "include.inp"
            deck.write_text("*INCLUDE, INPUT=mesh.inp\n", encoding="utf-8")
            result = run_abaqus_datacheck(str(deck))
            self.assertEqual(result.status, "needs_input")

    @patch("cae_agent.abaqus_runtime._run")
    def test_datacheck_rejects_zero_exit_without_evidence(self, run):
        run.return_value = (
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "Abaqus Error: The number of cpus (1) exceeds the number "
                    "of cpus available (-1).\n"
                    "Abaqus/Datacheck exited with error(s).\n"
                ),
                stderr="getWMI: Query for operating system name failed.\n",
            ),
            [],
        )
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "model.inp"
            deck.write_text("*HEADING\n", encoding="utf-8")
            result = run_abaqus_datacheck(str(deck), job_name="false_success")
        self.assertEqual(result.status, "failed")
        self.assertGreaterEqual(result.checks["error_markers"], 2)
        self.assertFalse(result.checks["completion_marker"])
        self.assertFalse(result.checks["dat_exists"])
        self.assertIn("required DAT evidence", result.error)
        self.assertTrue(any("WMI" in warning for warning in result.warnings))

    @patch("cae_agent.abaqus_runtime._run")
    def test_datacheck_accepts_completion_and_reports_warnings(self, run):
        def fake_run(arguments, cwd, timeout_seconds):
            (cwd / "portable_check.dat").write_text(
                "ANALYSIS DATACHECK COMPLETE\n"
                "WITH      3 WARNING MESSAGES ON THE DAT FILE\n",
                encoding="utf-8",
            )
            (cwd / "portable_check.msg").write_text(
                "datacheck message evidence\n", encoding="utf-8"
            )
            return (
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="Abaqus JOB portable_check COMPLETED\n",
                    stderr="",
                ),
                [],
            )

        run.side_effect = fake_run
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "model.inp"
            deck.write_text("*HEADING\n", encoding="utf-8")
            result = run_abaqus_datacheck(str(deck), job_name="portable_check")
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.checks["completion_marker"])
        self.assertTrue(result.checks["dat_exists"])
        self.assertTrue(result.checks["msg_exists"])
        self.assertEqual(result.checks["warning_messages"], 3)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
