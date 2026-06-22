from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "womenswear_workbench.py"


def _load_client():
    spec = importlib.util.spec_from_file_location("womenswear_workbench", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load client module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OnboardingTests(unittest.TestCase):
    def test_clean_install_command_shows_purchase_and_chat_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["CODEX_HOME"] = str(Path(temp_dir) / ".codex")
            env["APPDATA"] = str(Path(temp_dir) / "appdata")
            env["HOME"] = temp_dir
            env["USERPROFILE"] = temp_dir
            for name in (
                "WOMENSWEAR_CLOUD_CONFIG",
                "WOMENSWEAR_CLOUD_SERVER_URL",
                "WOMENSWEAR_CLOUD_API_KEY",
                "FLOWER_STREETSHOT_SERVER_URL",
                "FLOWER_STREETSHOT_API_KEY",
                "AI_FASHION_SERVER_URL",
                "AI_FASHION_API_KEY",
            ):
                env.pop(name, None)
            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "skills"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            message = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("catwde2", message)
            self.assertIn("server_url=", message)
            self.assertIn("api_key=", message)
            self.assertIn("config.toml", message)

    def test_missing_credentials_mentions_contact_and_chat_flow(self) -> None:
        client = _load_client()
        message = client._onboarding_message()
        self.assertIn("catwde2", message)
        self.assertIn("server_url=", message)
        self.assertIn("api_key=", message)
        self.assertIn("config.toml", message)

    def test_configure_saves_credentials_without_echoing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            secret = "test-secret-api-key"
            env = os.environ.copy()
            for name in (
                "WOMENSWEAR_CLOUD_CONFIG",
                "WOMENSWEAR_CLOUD_SERVER_URL",
                "WOMENSWEAR_CLOUD_API_KEY",
                "FLOWER_STREETSHOT_SERVER_URL",
                "FLOWER_STREETSHOT_API_KEY",
                "AI_FASHION_SERVER_URL",
                "AI_FASHION_API_KEY",
            ):
                env.pop(name, None)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "configure",
                    "--config",
                    str(config_path),
                    "--base-url",
                    "https://fashion.example.com/",
                    "--api-key",
                    secret,
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["configured"])
            self.assertNotIn(secret, result.stdout)
            with config_path.open("rb") as handle:
                config = tomllib.load(handle)
            self.assertEqual(config["service"]["server_url"], "https://fashion.example.com")
            self.assertEqual(config["service"]["api_key"], secret)

    def test_placeholder_credentials_show_onboarding_message(self) -> None:
        client = _load_client()
        with self.assertRaises(SystemExit) as raised:
            client._validated_credentials(
                "https://your-fashion-server.example.com",
                "your_api_key",
            )
        self.assertIn("catwde2", str(raised.exception))

    def test_default_write_target_is_this_skill_config(self) -> None:
        client = _load_client()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                client._config_path(None, for_write=True),
                SKILL_ROOT / "config.toml",
            )


if __name__ == "__main__":
    unittest.main()
