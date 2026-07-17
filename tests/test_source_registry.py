import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import source_registry


class SourceRegistryTests(unittest.TestCase):
    def test_runtime_override_is_separate_from_shipped_template(self):
        self.assertNotEqual(
            source_registry._LOCAL_REGISTRY_PATH.resolve(),
            source_registry._PROJECT_REGISTRY_PATH.resolve(),
        )

    def test_load_uses_shipped_template_when_local_override_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "source_registry.yaml"
            template.write_text("companies:\n  - company_name: Example\n    enabled: true\n")
            with (
                patch.object(source_registry, "_LOCAL_REGISTRY_PATH", root / "tracker" / "source_registry.yaml"),
                patch.object(source_registry, "_TEMPLATE_REGISTRY_PATH", template),
            ):
                registry = source_registry.load_registry()

        self.assertEqual(registry["companies"][0]["company_name"], "Example")

    def test_save_creates_local_override_without_changing_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "tracker" / "source_registry.yaml"
            template = root / "source_registry.yaml"
            template.write_text("companies: []\n")
            with (
                patch.object(source_registry, "_LOCAL_REGISTRY_PATH", local),
                patch.object(source_registry, "_TEMPLATE_REGISTRY_PATH", template),
            ):
                source_registry.save_registry({"companies": [{"company_name": "Local"}]})

            self.assertIn("Local", local.read_text())
            self.assertEqual(template.read_text(), "companies: []\n")


if __name__ == "__main__":
    unittest.main()
