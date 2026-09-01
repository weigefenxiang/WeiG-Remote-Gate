from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
ABI_MAP = ROOT / "native" / "mapper-abi-map.tsv"
CLASSES = ROOT / "native" / "mapper-build-classes.tsv"
RESOLVER = ROOT / "native" / "resolve-abi.sh"

# Union of package ABI directory names published by official OpenWrt package
# indexes from 17.01 through 25.12 that are relevant to this project.
OFFICIAL_ABIS = {
    "aarch64_armv8-a",
    "aarch64_cortex-a53",
    "aarch64_cortex-a72",
    "aarch64_cortex-a76",
    "aarch64_generic",
    "arc_arc700",
    "arc_archs",
    "arm_arm1176jzf-s_vfp",
    "arm_arm926ej-s",
    "arm_cortex-a15_neon-vfpv4",
    "arm_cortex-a5",
    "arm_cortex-a53_neon-vfpv4",
    "arm_cortex-a5_neon-vfpv4",
    "arm_cortex-a5_vfpv4",
    "arm_cortex-a7",
    "arm_cortex-a7_neon-vfpv4",
    "arm_cortex-a7_vfpv4",
    "arm_cortex-a8_neon",
    "arm_cortex-a8_vfpv3",
    "arm_cortex-a9",
    "arm_cortex-a9_neon",
    "arm_cortex-a9_vfpv3",
    "arm_cortex-a9_vfpv3-d16",
    "arm_fa526",
    "arm_mpcore",
    "arm_mpcore_vfp",
    "arm_xscale",
    "armeb_xscale",
    "i386_geode",
    "i386_i486",
    "i386_pentium",
    "i386_pentium-mmx",
    "i386_pentium4",
    "loongarch64_generic",
    "mips64_mips64r2",
    "mips64_octeon",
    "mips64_octeonplus",
    "mips64el_mips64r2",
    "mips_24kc",
    "mips_4kec",
    "mips_mips32",
    "mipsel_24kc",
    "mipsel_24kc_24kf",
    "mipsel_74kc",
    "mipsel_mips32",
    "powerpc64_e5500",
    "powerpc_464fp",
    "powerpc_8540",
    "powerpc_8548",
    "riscv64_generic",
    "riscv64_riscv64",
    "x86_64",
}


def rows(path):
    parsed = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        parsed.append(raw.split("\t"))
    return parsed


class MapperAbiMapTests(unittest.TestCase):
    def test_every_historical_official_abi_is_explicit(self):
        mapped = {row[0] for row in rows(ABI_MAP)}
        self.assertEqual(OFFICIAL_ABIS - mapped, set())

    def test_map_has_no_wildcards_or_duplicate_abi_keys(self):
        entries = rows(ABI_MAP)
        keys = [row[0] for row in entries]
        self.assertEqual(len(keys), len(set(keys)))
        for key in keys:
            self.assertNotIn("*", key)
            self.assertNotIn("?", key)
            self.assertFalse(key.endswith("_"))

    def test_every_abi_references_a_defined_build_class(self):
        classes = {row[0] for row in rows(CLASSES)}
        for abi, build_class, status in rows(ABI_MAP):
            with self.subTest(abi=abi):
                self.assertIn(build_class, classes)
                self.assertIn(status, {"cross-candidate", "sdk-required"})

    def test_cross_classes_use_static_musl_target_contract(self):
        for build_class, target, cflags, validation in rows(CLASSES):
            with self.subTest(build_class=build_class):
                if validation == "cross-build":
                    self.assertIn("-linux.", target)
                    self.assertTrue(target.endswith("-musl") or target.endswith("-musleabi"))
                    self.assertNotEqual(cflags, "-")
                else:
                    self.assertEqual(validation, "openwrt-sdk-required")
                    self.assertEqual(target, "-")

    def test_rare_abis_fail_safe_to_sdk_instead_of_guessing(self):
        mapping = {row[0]: row[1:] for row in rows(ABI_MAP)}
        self.assertEqual(mapping["arc_arc700"], ["sdk_arc", "sdk-required"])
        self.assertEqual(mapping["arc_archs"], ["sdk_arc", "sdk-required"])
        self.assertEqual(mapping["arm_fa526"], ["sdk_armv4", "sdk-required"])

    def test_exact_resolver_rejects_unknown_abi(self):
        result = subprocess.run(
            ["sh", str(RESOLVER), "abi", "mipsel_future_unknown"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_exact_resolver_returns_class_for_known_abi(self):
        result = subprocess.run(
            ["sh", str(RESOLVER), "full", "mipsel_24kc"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("mips32_le\tcross-candidate\tmipsel-linux.4.4-musl\t"))


if __name__ == "__main__":
    unittest.main()
