from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENTRY = (ROOT / "native" / "remote-gate-mapper-entry.c").read_text(encoding="utf-8")
MAKEFILE = (ROOT / "native" / "Makefile").read_text(encoding="utf-8")
PORTABLE = (ROOT / "native" / "build-portable.sh").read_text(encoding="utf-8")
SDK_PACKAGE = (ROOT / "native" / "openwrt-sdk-package" / "Makefile").read_text(encoding="utf-8")
SDK_BUILDER = (ROOT / "native" / "build-openwrt-sdk.sh").read_text(encoding="utf-8")
SMOKE = (ROOT / "native" / "smoke-portable.sh").read_text(encoding="utf-8")
SDK_RUNNER = (ROOT / "native" / "run-sdk-compat.sh").read_text(encoding="utf-8")


class MapperIdentityContractTests(unittest.TestCase):
    def test_entry_wrapper_does_not_modify_mapping_core_contract(self):
        self.assertIn('#define main remote_gate_mapper_main', ENTRY)
        self.assertIn('#include "remote-gate-mapper.c"', ENTRY)
        self.assertIn('strcmp(argv[1], "--version")', ENTRY)
        self.assertIn('remote-gate-mapper %s api=%d', ENTRY)
        self.assertIn('REMOTE_GATE_MAPPER_API 1', ENTRY)

    def test_all_build_paths_embed_project_version(self):
        self.assertIn('-DREMOTE_GATE_VERSION', MAKEFILE)
        self.assertIn('-DREMOTE_GATE_VERSION', PORTABLE)
        self.assertIn('-DREMOTE_GATE_VERSION', SDK_PACKAGE)
        self.assertIn('remote-gate-mapper-entry.c', SDK_BUILDER)
        self.assertIn('remote-gate-mapper-entry.c', SDK_PACKAGE)

    def test_portable_and_real_sdk_smoke_self_version(self):
        self.assertIn('--version', SMOKE)
        self.assertIn('remote-gate-mapper $version api=1', SMOKE)
        self.assertIn('--version', SDK_RUNNER)
        self.assertIn('remote-gate-mapper $version api=1', SDK_RUNNER)


if __name__ == "__main__":
    unittest.main()
