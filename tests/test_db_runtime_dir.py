import unittest
from pathlib import Path

from core.db import _sqlite_url_for_path


class DbRuntimeDirTests(unittest.TestCase):
    def test_sqlite_url_for_relative_runtime_db(self):
        self.assertEqual(
            _sqlite_url_for_path(Path("data") / "account_manager.db"),
            "sqlite:///data/account_manager.db",
        )

    def test_sqlite_url_for_absolute_runtime_db(self):
        self.assertEqual(
            _sqlite_url_for_path(Path("/tmp/autoreg/account_manager.db")),
            "sqlite:////tmp/autoreg/account_manager.db",
        )


if __name__ == "__main__":
    unittest.main()
