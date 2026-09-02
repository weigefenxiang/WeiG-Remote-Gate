import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
README_ZH = (ROOT / "translations" / "README.zh-CN.md").read_text(encoding="utf-8")


class DocumentationContractTests(unittest.TestCase):
    def test_readmes_point_to_systemic_invariants(self):
        self.assertIn("docs/SYSTEMIC-INVARIANTS.md", README)
        self.assertIn("docs/SYSTEMIC-INVARIANTS.md", README_ZH)

    def test_private_cgnat_never_returns_as_public_access_try(self):
        forbidden = (
            "Private/CGNAT Try",
            "private/CGNAT IPv4 `Try`",
            "Private / CGNAT IPv4 `Try`",
            "供手工实验使用的 Private / CGNAT",
        )
        for source in (README, README_ZH):
            for text in forbidden:
                self.assertNotIn(text, source)
        self.assertIn("not a selectable public Access Endpoint", README)
        self.assertIn("不是可选择的公网 Access Endpoint", README_ZH)

    def test_readmes_keep_access_and_exit_independent(self):
        self.assertIn("independent from the Access Gate family", README)
        self.assertIn("与 Access Gate Family 独立", README_ZH)
        for mode in ("none", "ipv4", "ipv6", "dual"):
            self.assertIn(mode, README)
            self.assertIn(mode, README_ZH)

    def test_readmes_keep_current_source_authority_terms(self):
        self.assertIn("Cloudflare HTTP observation", README)
        self.assertIn("carrier candidate", README)
        self.assertIn("Cloudflare HTTP Observation", README_ZH)
        self.assertIn("Carrier Candidate", README_ZH)
        self.assertNotIn("Network Probe (`heuristic`)", README_ZH)
        self.assertNotIn("Cloudflare Observation (`verified`)", README_ZH)

    def test_readmes_describe_ci_layers_without_routine_browser_drift(self):
        self.assertIn("Routine `v0.3.x CI`", README)
        self.assertIn("Release Browser Validation", README)
        self.assertIn("Routine `v0.3.x CI`", README_ZH)
        self.assertIn("Release Browser Validation", README_ZH)
        self.assertNotIn("Core + Native cross-build + Chromium regression CI", README)
        self.assertNotIn("Core + Chromium Regression CI", README_ZH)

    def test_readmes_keep_shared_path_card_contract(self):
        for source in (README, README_ZH):
            self.assertIn("PathCard", source)
            self.assertIn("FamilyPathBlock", source)
            self.assertIn("fit-text.js", source)
            self.assertIn("Split WAN", source)
            self.assertIn("Split Exit", source)

    def test_hardware_summary_does_not_regress_mapped_validation(self):
        self.assertIn("IPv4 Mapped Gate CLOSED", README)
        self.assertIn("IPv4 Mapped Gate CLOSED", README_ZH)
        self.assertIn("PPPoE", README)
        self.assertIn("PPPoE", README_ZH)
        self.assertIn("fw4/nftables", README)
        self.assertIn("fw4/nftables", README_ZH)


if __name__ == "__main__":
    unittest.main()
