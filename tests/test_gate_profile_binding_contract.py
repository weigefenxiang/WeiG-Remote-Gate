import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = (ROOT / "server/app/static/js/gate-controls.js").read_text(encoding="utf-8")
QUEUE = (ROOT / "server/app/gate.py").read_text(encoding="utf-8")
SERVER = (ROOT / "server/remote-gate.py").read_text(encoding="utf-8")
BROWSER = (ROOT / "tests/browser_gate_profile_binding.mjs").read_text(encoding="utf-8")
CORE_CI = (ROOT / ".github/workflows/v030-ci.yml").read_text(encoding="utf-8")
RELEASE_CI = (ROOT / ".github/workflows/browser-release.yml").read_text(encoding="utf-8")
BROWSER_MATRIX_CI = (ROOT / ".github/workflows/browser-matrix.yml").read_text(encoding="utf-8")


class GateProfileBindingContractTests(unittest.TestCase):
    def test_browser_owner_covers_exact_source_and_access_profile_identity(self):
        self.assertIn("198.51.100.44", BROWSER)
        self.assertIn("device: 'pppoe-WAN'", BROWSER)
        self.assertIn("ingress_port: 57470", BROWSER)
        self.assertIn("endpoint.service_port = 53127", BROWSER)
        self.assertIn("scope: 'wg'", BROWSER)
        self.assertIn("[data-scope=\"wg_ping\"]", BROWSER)
        self.assertIn("OPEN · OTHER ACCESS PATH", BROWSER)
        self.assertIn("OPEN ELSEWHERE", BROWSER)

    def test_mapped_ingress_and_wireguard_service_ports_are_behaviorally_distinct(self):
        self.assertIn("endpoint.external_port = 45678", BROWSER)
        self.assertIn("endpoint.ingress_port = 57470", BROWSER)
        self.assertIn("endpoint.service_port = 53127", BROWSER)
        self.assertIn("runtimeServicePort = 53128", BROWSER)
        self.assertIn("matching mapped ingress/service profile", BROWSER)
        self.assertIn("service-port drift", BROWSER)
        self.assertIn("AUTHORIZED", BROWSER)
        self.assertIn("OPEN · OTHER ACCESS PATH", BROWSER)
        for stale in ("ingress_port || wg_port", "ingress_port || item.wg_port", "ingress_port || legacy.wg_port"):
            self.assertNotIn(stale, GATE)

    def test_profile_mismatch_is_close_only_and_never_auto_activates(self):
        self.assertIn("Close must remain available", BROWSER)
        self.assertIn("replacement Activate must remain hidden", BROWSER)
        self.assertIn("orb must Close the active runtime", BROWSER)
        self.assertIn("profile/family selection changes posted Activate", BROWSER)
        self.assertIn("source mismatch posted Activate", BROWSER)
        self.assertIn("service-port drift posted Activate", BROWSER)
        self.assertIn("Dual partial state posted Activate", BROWSER)

    def test_access_profile_authority_is_independent_from_internet_exit(self):
        self.assertIn("chooseLanOnly(page)", BROWSER)
        self.assertIn("matching mapped ingress/service profile", BROWSER)
        self.assertIn("AUTHORIZED", BROWSER)

    def test_failed_dashboard_refresh_revokes_cached_browser_authority(self):
        self.assertIn("STATUS UNKNOWN", BROWSER)
        self.assertIn("failed dashboard refresh must revoke cached OPEN authority", BROWSER)
        self.assertIn("failed refresh should preserve safe Close from last-known runtime hint", BROWSER)
        self.assertIn("failed refresh must keep Activate disabled", BROWSER)
        self.assertIn("failed dashboard refresh posted Activate", BROWSER)

    def test_server_and_browser_keep_close_before_replacement_activate_boundary(self):
        self.assertIn("gate_close_required", QUEUE)
        self.assertIn("gate_close_required", SERVER)
        self.assertIn("gate_close_required", GATE)
        self.assertIn("Remote access is already active", GATE)
        self.assertIn("Close must remain available", BROWSER)

    def test_browser_regression_covers_wireguard_family_partial_and_refresh_conflicts(self):
        self.assertIn("listen_port: 41194", BROWSER)
        self.assertIn("selectOption('WG_ALT')", BROWSER)
        self.assertIn("[data-family=\"ipv6\"]", BROWSER)
        self.assertIn("OPEN · PARTIAL ACCESS", BROWSER)
        self.assertIn("PARTIAL OPEN", BROWSER)
        self.assertIn("STATUS UNKNOWN", BROWSER)
        self.assertIn("activatePosts() === 0", BROWSER)

    def test_browser_execution_uses_shared_matrix_while_release_stays_main_only(self):
        self.assertIn("node --check tests/browser_gate_profile_binding.mjs", CORE_CI)
        self.assertNotIn("node tests/browser_gate_profile_binding.mjs", CORE_CI)
        self.assertIn("node tests/browser_gate_profile_binding.mjs", BROWSER_MATRIX_CI)
        self.assertIn("uses: ./.github/workflows/browser-matrix.yml", RELEASE_CI)
        self.assertIn("if: github.ref == 'refs/heads/main'", RELEASE_CI)


if __name__ == "__main__":
    unittest.main()
