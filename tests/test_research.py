from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cae_agent.diagnostics import diagnose_cae_failure
from cae_agent.research import (
    evaluate_failure_research,
    prepare_failure_research,
    record_verified_failure_rule,
)


class FailureResearchTests(unittest.TestCase):
    ERROR_TEXT = "Abaqus Error: CUSTOM FAILURE 9917 at element 42"

    def test_prepare_prefers_official_domains(self):
        result = prepare_failure_research(
            application="abaqus",
            error_text=self.ERROR_TEXT,
            stage="solve",
        )
        self.assertEqual(result.status, "succeeded")
        queries = result.checks["search_queries"]
        self.assertTrue(any("docs.software.vt.edu" in query for query in queries))
        self.assertEqual(len(result.checks["fingerprint_sha256"]), 64)

    def test_evaluate_ranks_official_source_and_marks_candidate(self):
        result = evaluate_failure_research(
            application="hypermesh",
            error_text="Thin solid mesh failed because source face is invalid",
            candidates=[
                {
                    "url": "https://random.example.net/post",
                    "title": "Mesh tip",
                    "excerpt": "Try changing everything.",
                    "recommended_actions": ["Change the geometry."],
                },
                {
                    "url": (
                        "https://2025.help.altair.com/2025/hwdesktop/hwx/topics/"
                        "pre_processing/meshing/thin_solid_mesh_create_t.htm"
                    ),
                    "title": "Create Thin Solid Mesh",
                    "excerpt": (
                        "Thin solid source and target faces must be identifiable and "
                        "connected by side faces."
                    ),
                    "cause": "The selected source or target face is invalid.",
                    "recommended_actions": [
                        "Select valid opposite source and target faces."
                    ],
                    "product_version": "2025",
                },
            ],
        )
        self.assertEqual(result.status, "succeeded")
        candidate = result.checks["candidate_rule"]
        self.assertEqual(candidate["knowledge_status"], "candidate-unverified")
        self.assertEqual(
            result.checks["ranked_sources"][0]["source_type"],
            "official-documentation",
        )

    def test_verified_rule_round_trip_into_diagnosis(self):
        evaluated = evaluate_failure_research(
            application="abaqus",
            error_text=self.ERROR_TEXT,
            candidates=[
                {
                    "url": (
                        "https://docs.software.vt.edu/abaqusv2025/English/"
                        "SIMACAECAERefMap/simacae-c-anaconcmonitor.htm"
                    ),
                    "title": "Monitoring an Abaqus analysis job",
                    "excerpt": (
                        "CUSTOM FAILURE 9917 diagnostics are written to job files."
                    ),
                    "cause": "A custom verified test failure.",
                    "recommended_actions": [
                        "Run a bounded datacheck and inspect the diagnostic files."
                    ],
                    "product_version": "2025",
                }
            ],
        )
        candidate = evaluated.checks["candidate_rule"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failure-rules.json"
            preview = record_verified_failure_rule(
                registry_path=str(path),
                candidate_rule=candidate,
                verification_evidence=["datacheck-before.dat", "datacheck-after.dat"],
                idempotency_key="custom-9917-pass-1",
            )
            self.assertEqual(preview.status, "needs_confirmation")
            committed = record_verified_failure_rule(
                registry_path=str(path),
                candidate_rule=candidate,
                verification_evidence=["datacheck-before.dat", "datacheck-after.dat"],
                idempotency_key="custom-9917-pass-1",
                confirm_write=True,
            )
            self.assertEqual(committed.status, "succeeded")
            diagnosed = diagnose_cae_failure(
                application="abaqus",
                log_text=self.ERROR_TEXT,
                knowledge_paths=[str(path)],
            )
        learned = [
            issue for issue in diagnosed.checks["matched_issues"]
            if issue["knowledge_origin"] == "verified-web-research"
        ]
        self.assertEqual(len(learned), 1)
        self.assertEqual(diagnosed.checks["learned_knowledge_rules"], 1)
        self.assertTrue(learned[0]["sources"])


if __name__ == "__main__":
    unittest.main()
