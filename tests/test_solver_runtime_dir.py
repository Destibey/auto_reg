import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import solver_manager


class SolverRuntimeDirTests(unittest.TestCase):
    def test_solver_log_uses_runtime_dir_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"APP_RUNTIME_DIR": tmp}):
                self.assertEqual(solver_manager._solver_log_path(), str(Path(tmp) / "logs" / "solver.log"))
                self.assertTrue((Path(tmp) / "logs").is_dir())

    def test_solver_settings_can_be_read_from_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "LOCAL_SOLVER_URL=http://127.0.0.1:8899",
                        "SOLVER_PORT=8899",
                        "SOLVER_BIND_HOST=127.0.0.1",
                        "SOLVER_BROWSER_TYPE=chromium",
                        "SOLVER_THREAD=1",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(solver_manager, "_ENV_FILE", env_file):
                with mock.patch.dict("os.environ", {}, clear=True):
                    self.assertEqual(solver_manager._solver_url(), "http://127.0.0.1:8899")
                    self.assertEqual(solver_manager._solver_port(), 8899)
                    self.assertEqual(solver_manager._solver_bind_host(), "127.0.0.1")
                    self.assertEqual(solver_manager._solver_browser_type(), "chromium")
                    self.assertEqual(solver_manager._solver_thread(), 1)


if __name__ == "__main__":
    unittest.main()
