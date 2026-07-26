from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cae_agent.hypermesh import (
    check_hm_mesh_quality,
    mesh_hm_solids,
    smooth_hm_solid_mesh,
)


class HyperMeshAutomationTests(unittest.TestCase):
    def test_solid_map_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.hm"
            model.write_text("portable-placeholder", encoding="utf-8")
            result = mesh_hm_solids(
                str(model),
                str(root / "meshed.hm"),
                [3, 1, 3],
                1.5,
            )
        self.assertEqual(result.status, "needs_confirmation")
        self.assertEqual(result.checks["solid_ids"], [1, 3])

    def test_solid_map_rejects_invalid_size(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.hm"
            model.write_text("portable-placeholder", encoding="utf-8")
            result = mesh_hm_solids(
                str(model),
                str(Path(directory) / "meshed.hm"),
                [1],
                0,
            )
        self.assertEqual(result.status, "failed")
        self.assertIn("element_size", result.error)

    def test_quality_rejects_invalid_jacobian(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.hm"
            model.write_text("portable-placeholder", encoding="utf-8")
            result = check_hm_mesh_quality(str(model), jacobian_min=1.1)
        self.assertEqual(result.status, "failed")
        self.assertIn("jacobian_min", result.error)

    def test_smoothing_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.hm"
            model.write_text("portable-placeholder", encoding="utf-8")
            result = smooth_hm_solid_mesh(
                str(model),
                str(root / "smoothed.hm"),
                [20, 10],
            )
        self.assertEqual(result.status, "needs_confirmation")
        self.assertEqual(result.checks["element_ids"], [10, 20])


if __name__ == "__main__":
    unittest.main()
