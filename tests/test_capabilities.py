"""Machine-readable capability document for the sole public PXL profile."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "spec/conformance/capabilities/pxl-v1.json"
ALLOWED_KEYS = set([
    "capabilities_version", "compiler_id", "compiler_version",
    "conformance_profile", "language_versions", "error_code_ranges",
    "png_input_profile",
])


class CapabilitiesSchemaTest(unittest.TestCase):
    def setUp(self):
        self.raw = FIXTURE.read_bytes()
        self.data = json.loads(self.raw.decode("utf-8"))

    def test_canonical_text_envelope(self):
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.raw.endswith(b"\n"))
        self.assertFalse(self.raw.endswith(b"\n\n"))

    def test_exact_current_profile(self):
        self.assertEqual(ALLOWED_KEYS, set(self.data))
        self.assertEqual(1, self.data["capabilities_version"])
        self.assertEqual("0.999.4", self.data["compiler_version"])
        self.assertEqual("pxl-v1", self.data["conformance_profile"])
        self.assertEqual([1], self.data["language_versions"])
        self.assertEqual({"1": {"min": "PXL001", "max": "PXL012"}},
                         self.data["error_code_ranges"])
        self.assertEqual("pxl-png", self.data["png_input_profile"])


if __name__ == "__main__":
    unittest.main()
