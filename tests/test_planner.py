from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cae_agent.planner import get_cae_capabilities, plan_next_action


class PlannerTests(unittest.TestCase):
    def test_capabilities_are_explicit_about_runtime_adapters(self):
        result = get_cae_capabilities()
        self.assertEqual(result.status, "succeeded")
        self.assertIn(
            result.checks["stages"]["mesh"]["status"], {"available", "unavailable"}
        )
        self.assertIn(
            result.checks["stages"]["solve"]["status"],
            {"available", "partial", "unavailable"},
        )
        self.assertIn(
            result.checks["stages"]["post"]["status"],
            {"available", "partial", "unavailable"},
        )
        self.assertIn("hypermesh", result.checks["runtime"])
        self.assertIn("abaqus", result.checks["runtime"])

    def test_repair_manifest_plans_deck_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "repair-elsets.inp"
            deck.write_text("*HEADING\n", encoding="utf-8")
            manifest = root / "case.json"
            manifest.write_text(
                json.dumps(
                    {
                        "case_id": "repair",
                        "stages": {
                            "cad": {"status": "passed"},
                            "mesh": {"status": "passed"},
                            "deck": {"status": "pending"},
                            "solve": {"status": "pending"},
                            "post": {"status": "pending"},
                        },
                        "artifacts": [
                            {"path": deck.name, "role": "abaqus-deck-elset"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = plan_next_action(str(manifest))
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.checks["current_stage"], "deck")
            self.assertEqual(result.checks["tool"], "validate_abaqus_mesh")
            self.assertEqual(
                Path(result.checks["arguments"]["input_path"]), deck.resolve()
            )

    def test_solver_stage_requires_approval_and_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "case.json"
            manifest.write_text(
                json.dumps(
                    {
                        "case_id": "solve-case",
                        "stages": {
                            "cad": {"status": "passed"},
                            "mesh": {"status": "passed"},
                            "deck": {"status": "passed"},
                            "solve": {"status": "pending"},
                            "post": {"status": "pending"},
                        },
                        "artifacts": [],
                    }
                ),
                encoding="utf-8",
            )
            result = plan_next_action(str(manifest))
            self.assertEqual(result.status, "needs_input")
            self.assertEqual(result.checks["current_stage"], "solve")
            self.assertTrue(result.checks["approval_required"])


if __name__ == "__main__":
    unittest.main()
