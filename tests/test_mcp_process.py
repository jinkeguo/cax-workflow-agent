from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class McpProcessTests(unittest.TestCase):
    def test_real_deck_validation_through_stdio_mcp(self):
        deck_text = """*NODE
1,0,0,0
2,1,0,0
3,1,1,0
4,0,1,0
5,0,0,1
6,1,0,1
7,1,1,1
8,0,1,1
*ELEMENT,TYPE=C3D8R,ELSET=PLY_01
1,1,2,3,4,5,6,7,8
"""
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "portable.inp"
            deck.write_text(deck_text, encoding="utf-8")
            request = {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "validate_abaqus_mesh",
                    "arguments": {
                        "input_path": str(deck),
                        "expected_type": "C3D8R",
                        "expected_elements": 1,
                    },
                },
            }
            runner = Path(__file__).resolve().parents[1] / "mcp" / "run_mcp.py"
            process = subprocess.run(
                [sys.executable, str(runner)],
                input=json.dumps(request) + "\n",
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            )
            response = json.loads(process.stdout)
            result = response["result"]
            self.assertFalse(result["isError"])
            self.assertEqual(result["structuredContent"]["status"], "succeeded")
            self.assertEqual(result["structuredContent"]["checks"]["elements"], 1)
            self.assertEqual(
                result["structuredContent"]["checks"]["element_types"], {"C3D8R": 1}
            )


if __name__ == "__main__":
    unittest.main()
