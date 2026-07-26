from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cae_agent.manifest import record_case_stage


class ManifestWriterTests(unittest.TestCase):
    def test_preview_write_and_idempotent_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            path.write_text(
                json.dumps(
                    {
                        "case_id": "writer-test",
                        "stages": {
                            "cad": {"status": "passed", "evidence": []},
                            "mesh": {"status": "in_progress", "evidence": []},
                        },
                        "artifacts": [],
                    }
                ),
                encoding="utf-8",
            )
            original = path.read_bytes()
            digest = hashlib.sha256(original).hexdigest()
            preview = record_case_stage(
                str(path),
                "mesh",
                "passed",
                ["validator: PASS"],
                "mesh-pass-1",
                expected_manifest_sha256=digest,
            )
            self.assertEqual(preview.status, "needs_input")
            self.assertEqual(path.read_bytes(), original)

            written = record_case_stage(
                str(path),
                "mesh",
                "passed",
                ["validator: PASS"],
                "mesh-pass-1",
                expected_manifest_sha256=digest,
                confirm_write=True,
            )
            self.assertEqual(written.status, "succeeded")
            self.assertEqual(json.loads(path.read_text())["stages"]["mesh"]["status"], "passed")

            replay = record_case_stage(
                str(path),
                "mesh",
                "passed",
                ["validator: PASS"],
                "mesh-pass-1",
                confirm_write=True,
            )
            self.assertEqual(replay.status, "succeeded")
            self.assertTrue(replay.checks["idempotent_replay"])


if __name__ == "__main__":
    unittest.main()
