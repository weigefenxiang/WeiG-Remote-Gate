from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "native" / "sdk-compat-matrix.tsv"
ABI_MAP = ROOT / "native" / "mapper-abi-map.tsv"
RUNNER = (ROOT / "native" / "run-sdk-compat.sh").read_text(encoding="utf-8")
MAIN_CI = (ROOT / ".github" / "workflows" / "v030-ci.yml").read_text(encoding="utf-8")
SDK_CI = (ROOT / ".github" / "workflows" / "sdk-compat.yml").read_text(encoding="utf-8")


def rows(path: Path, columns: int):
    result = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) != columns:
            raise AssertionError(f"{path}: expected {columns} columns: {raw}")
        result.append(parts)
    return result


class SdkCompatibilityMatrixTests(unittest.TestCase):
    def test_matrix_is_exact_and_trusted(self):
        entries = rows(MATRIX, 8)
        self.assertGreaterEqual(len(entries), 6)
        ids = [entry[0] for entry in entries]
        self.assertEqual(len(ids), len(set(ids)))
        known_abis = {entry[0] for entry in rows(ABI_MAP, 3)}

        for sample, family, release, target, abi, archive, sha256, url in entries:
            self.assertRegex(sample, r"^[A-Za-z0-9_.+-]+$")
            self.assertIn(family, {"lede", "openwrt", "immortalwrt"})
            self.assertRegex(release, r"^[0-9A-Za-z._+-]+$")
            self.assertRegex(target, r"^[A-Za-z0-9_./+-]+$")
            self.assertIn(abi, known_abis)
            self.assertIn(archive, {"xz", "zst"})
            self.assertRegex(sha256, r"^[0-9a-f]{64}$")
            if family in {"lede", "openwrt"}:
                self.assertTrue(url.startswith("https://downloads.openwrt.org/releases/"))
            else:
                self.assertTrue(url.startswith("https://downloads.immortalwrt.org/releases/"))
            self.assertTrue(url.endswith(".tar.xz") if archive == "xz" else url.endswith(".tar.zst"))

    def test_release_eras_and_forks_are_covered(self):
        samples = {entry[0] for entry in rows(MATRIX, 8)}
        expected = {
            "lede-17.01.7-x86_64",
            "openwrt-19.07.10-x86_64",
            "openwrt-21.02.7-x86_64",
            "openwrt-24.10.5-x86_64",
            "openwrt-25.12.5-x86_64",
            "immortalwrt-24.10.5-x86_64",
        }
        self.assertTrue(expected.issubset(samples))

    def test_main_ci_uses_centralized_legacy_sample(self):
        self.assertIn("sh native/run-sdk-compat.sh lede-17.01.7-x86_64", MAIN_CI)
        self.assertNotIn("lede-sdk-17.01.7-x86-64_gcc", MAIN_CI)

    def test_scheduled_workflow_covers_modern_samples(self):
        for sample in (
            "openwrt-19.07.10-x86_64",
            "openwrt-21.02.7-x86_64",
            "openwrt-24.10.5-x86_64",
            "openwrt-25.12.5-x86_64",
            "immortalwrt-24.10.5-x86_64",
        ):
            self.assertIn(sample, SDK_CI)
        self.assertIn("workflow_dispatch:", SDK_CI)
        self.assertIn("schedule:", SDK_CI)
        self.assertIn("fail-fast: false", SDK_CI)

    def test_runner_verifies_hash_and_restricts_hosts(self):
        self.assertIn("sha256sum -c -", RUNNER)
        self.assertIn("https://downloads.openwrt.org/releases/", RUNNER)
        self.assertIn("https://downloads.immortalwrt.org/releases/", RUNNER)
        self.assertIn("build-openwrt-sdk.sh", RUNNER)
        self.assertNotIn("eval ", RUNNER)


if __name__ == "__main__":
    unittest.main()
