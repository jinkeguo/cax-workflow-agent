from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cae_agent.abaqus_runtime import (
    ABAQUS_COMMAND_ENV,
    abaqus_installation_status,
    discover_abaqus_command,
)
from cae_agent.hypermesh import (
    ABAQUS_TEMPLATE_ENV,
    HM_EXECUTABLE_ENV,
    discover_abaqus_template,
    discover_hypermesh_executable,
    hypermesh_installation_status,
)


class RuntimeDiscoveryTests(unittest.TestCase):
    def test_explicit_hypermesh_paths_win(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "hmopengl.exe"
            template = root / "standard.3d"
            executable.write_bytes(b"test")
            template.write_text("test", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    HM_EXECUTABLE_ENV: str(executable),
                    ABAQUS_TEMPLATE_ENV: str(template),
                },
                clear=False,
            ):
                self.assertEqual(discover_hypermesh_executable(), executable.resolve())
                self.assertEqual(discover_abaqus_template(), template.resolve())
                status = hypermesh_installation_status()
                self.assertTrue(status["executable_exists"])
                self.assertTrue(status["abaqus_template_exists"])

    def test_explicit_abaqus_command_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            command = Path(directory) / "abaqus.bat"
            command.write_text("@echo off\n", encoding="utf-8")
            with patch.dict(
                os.environ, {ABAQUS_COMMAND_ENV: str(command)}, clear=False
            ):
                self.assertEqual(discover_abaqus_command(), command.resolve())
                self.assertTrue(abaqus_installation_status()["command_exists"])


if __name__ == "__main__":
    unittest.main()
