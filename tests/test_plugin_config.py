from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path


class PluginConfigTests(unittest.TestCase):
    def test_solidworks_bridge_is_packaged_with_adapter(self):
        import cae_agent

        package_root = Path(cae_agent.__file__).resolve().parent
        self.assertTrue((package_root / "solidworks_bridge.ps1").is_file())
        self.assertTrue((package_root / "solidworks_bridge.py").is_file())

    def test_plugin_mcp_command_starts_and_lists_tools(self):
        config_path = Path(__file__).resolve().parents[1] / ".mcp.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        server = config["mcpServers"]["cae-workflow"]
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        process = subprocess.run(
            [server["command"], *server["args"]],
            input="\n".join(json.dumps(item) for item in requests) + "\n",
            text=True,
            capture_output=True,
            env={**os.environ, **server.get("env", {})},
            cwd=(config_path.parent / server.get("cwd", ".")).resolve(),
            timeout=20,
            check=True,
        )
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(
            responses[0]["result"]["serverInfo"]["name"], "cax-workflow-agent"
        )
        tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertEqual(
            tool_names,
            {
                "inspect_hm_model",
                "mesh_hm_solids",
                "check_hm_mesh_quality",
                "smooth_hm_solid_mesh",
                "export_abaqus_deck",
                "ensure_component_elsets",
                "validate_abaqus_mesh",
                "get_case_status",
                "get_cae_capabilities",
                "plan_next_action",
                "record_case_stage",
                "get_abaqus_environment",
                "run_abaqus_datacheck",
                "inspect_abaqus_job",
                "submit_abaqus_job",
                "monitor_abaqus_job",
                "cancel_abaqus_job",
                "retry_abaqus_job",
                "summarize_abaqus_odb",
                "extract_abaqus_field",
                "extract_abaqus_path",
                "render_abaqus_contour",
                "extract_abaqus_failure_indices",
                "get_solidworks_environment",
                "test_solidworks_connection",
                "inspect_solidworks_document",
                "instantiate_solidworks_template",
                "export_solidworks_document",
                "diagnose_cae_failure",
                "prepare_failure_research",
                "evaluate_failure_research",
                "record_verified_failure_rule",
            },
        )


if __name__ == "__main__":
    unittest.main()
