from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cae_agent.abaqus import ensure_component_elsets, validate_abaqus_mesh
from cae_agent.mcp_server import handle


class AdapterTests(unittest.TestCase):
    def test_protocol_initialize_and_tool_list(self):
        initialized = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-06-18")
        listed = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(listed["result"]["tools"]), 32)

    def test_validate_small_hex_and_add_elset(self):
        text = """**HW_COMPONENT ID=1 NAME=PLY_01
*NODE
1,0,0,0
2,1,0,0
3,1,1,0
4,0,1,0
5,0,0,1
6,1,0,1
7,1,1,1
8,0,1,1
*ELEMENT,TYPE=C3D8R
1,1,2,3,4,5,6,7,8
"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.inp"
            target = Path(directory) / "target.inp"
            source.write_text(text, encoding="utf-8")
            converted = ensure_component_elsets(str(source), str(target))
            self.assertEqual(converted.status, "succeeded")
            self.assertIn("ELSET=PLY_01", target.read_text(encoding="utf-8"))
            checked = validate_abaqus_mesh(str(target), "C3D8R", 1)
            self.assertEqual(checked.status, "succeeded")
            self.assertEqual(checked.checks["hex_nonpositive"], 0)

    def test_stdio_round_trip(self):
        request = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}) + "\n"
        process = subprocess.run(
            [sys.executable, "-m", "cae_agent.mcp_server"],
            input=request,
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )
        response = json.loads(process.stdout)
        self.assertEqual(response["id"], 3)
        self.assertEqual(response["result"], {})


if __name__ == "__main__":
    unittest.main()
