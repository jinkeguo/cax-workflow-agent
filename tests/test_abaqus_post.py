from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cae_agent.abaqus_post import (
    extract_abaqus_field,
    extract_abaqus_path,
    render_abaqus_contour,
)


class AbaqusPostTests(unittest.TestCase):
    def test_field_rejects_component_and_invariant_together(self):
        with tempfile.TemporaryDirectory() as directory:
            odb = Path(directory) / "model.odb"
            odb.write_bytes(b"portable-placeholder")
            result = extract_abaqus_field(
                str(odb),
                str(Path(directory) / "field.json"),
                "S",
                component="S11",
                invariant="mises",
            )
        self.assertEqual(result.status, "failed")
        self.assertIn("not both", result.error)

    def test_path_requires_two_positive_node_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            odb = Path(directory) / "model.odb"
            odb.write_bytes(b"portable-placeholder")
            result = extract_abaqus_path(
                str(odb),
                str(Path(directory) / "path.json"),
                "PART-1-1",
                [1],
                "U",
            )
        self.assertEqual(result.status, "failed")
        self.assertIn("at least two", result.error)

    def test_contour_rejects_unknown_position(self):
        with tempfile.TemporaryDirectory() as directory:
            odb = Path(directory) / "model.odb"
            odb.write_bytes(b"portable-placeholder")
            result = render_abaqus_contour(
                str(odb),
                str(Path(directory) / "contour.png"),
                "S",
                "surface",
            )
        self.assertEqual(result.status, "failed")
        self.assertIn("position", result.error)


if __name__ == "__main__":
    unittest.main()
