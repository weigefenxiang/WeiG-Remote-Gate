from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "openwrt" / "remote-gate-mapping.sh"
FIREWALL = ROOT / "openwrt" / "remote-gate-firewall.sh"
BACKENDS = ROOT / "openwrt" / "remote-gate-firewall-backends.sh"


class MappingRuntimeIntegrityTests(unittest.TestCase):
    def _environment(self, base: Path, installer_ok: bool):
        lib = base / "lib"
        state = base / "state"
        fakebin = base / "bin"
        lib.mkdir()
        state.mkdir()
        fakebin.mkdir()

        mapper = lib / "remote-gate-mapper"
        mapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        mapper.chmod(0o755)

        services = lib / "remote-gate-service-registry.sh"
        services.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        services.chmod(0o755)

        installer = lib / "remote-gate-mapper-install.sh"
        installer.write_text(
            "#!/bin/sh\n"
            "[ \"${1:-}\" = current ] || exit 2\n"
            f"exit {0 if installer_ok else 1}\n",
            encoding="utf-8",
        )
        installer.chmod(0o755)

        jsonfilter = fakebin / "jsonfilter"
        jsonfilter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        jsonfilter.chmod(0o755)

        env = os.environ.copy()
        env.update(
            {
                "REMOTE_GATE_LIB_DIR": str(lib),
                "REMOTE_GATE_MAPPING_STATE_DIR": str(state),
                "REMOTE_GATE_MAPPER_BIN": str(mapper),
                "REMOTE_GATE_MAPPER_INSTALLER": str(installer),
                "REMOTE_GATE_SERVICE_REGISTRY": str(services),
                "REMOTE_GATE_CONFIG_FILE": str(base / "missing.conf"),
                "PATH": f"{fakebin}:{env['PATH']}",
            }
        )
        return env

    def test_available_requires_delivery_current(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._environment(Path(td), installer_ok=True)
            result = subprocess.run(["sh", str(MAPPING), "available"], env=env)
            self.assertEqual(result.returncode, 0)

    def test_invalid_delivery_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._environment(Path(td), installer_ok=False)
            result = subprocess.run(["sh", str(MAPPING), "available"], env=env)
            self.assertNotEqual(result.returncode, 0)
            status = subprocess.run(
                ["sh", str(MAPPING), "status-json"],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            ).stdout
            self.assertIn('"available":false', status)
            self.assertIn('"detail":"mapper-integrity-unavailable"', status)

    def test_runtime_passes_actual_mapper_path_to_integrity_helper(self):
        source = MAPPING.read_text(encoding="utf-8")
        self.assertIn('MAPPER_INSTALLER="${REMOTE_GATE_MAPPER_INSTALLER:-$LIB_DIR/remote-gate-mapper-install.sh}"', source)
        self.assertIn('REMOTE_GATE_MAPPER_DEST="$MAPPER_BIN" sh "$MAPPER_INSTALLER" current', source)

    def test_changed_mapped_ingress_revokes_old_authorization(self):
        firewall = FIREWALL.read_text(encoding="utf-8")
        backends = BACKENDS.read_text(encoding="utf-8")
        protected = firewall.split("protected_ingress_current() {", 1)[1].split("fw3_ipv6_capable()", 1)[0]
        reconcile = backends.split("reconcile_family() {", 1)[1].split("reconcile_policy()", 1)[0]

        self.assertIn('grep -Fqx "${rg_dev}|${rg_port}" "$MAPPED_INGRESS_V4_FILE"', protected)
        self.assertIn('auth_record_policy_current "$rg_family" "$rg_record"', reconcile)
        self.assertIn('authorization revoked because protected WAN/ingress policy changed', reconcile)
        self.assertIn('rm -f "$rg_file"', reconcile)
        self.assertNotIn("resolve-current", reconcile)

    def test_current_mapping_requires_live_owned_mapper_process(self):
        source = MAPPING.read_text(encoding="utf-8")
        helper = source.split("status_process_current() {", 1)[1].split("stop_key()", 1)[0]
        control = source.split("status_control_tuple() {", 1)[1].split("ingress_pairs()", 1)[0]
        ingress = source.split("ingress_pairs() {", 1)[1].split("ingress_ports()", 1)[0]
        record = source.split("mapping_record() {", 1)[1].split("resolve_current()", 1)[0]
        status = source.split("status_json() {", 1)[1].split('case "${1:-status-json}"', 1)[0]

        self.assertIn('owned_pid "$pid" "$status"', helper)
        self.assertIn('status_process_current "$status" || return 1', control)
        self.assertIn('status_process_current "$status" || continue', ingress)
        self.assertIn('status_process_current "$status" || return 1', record)
        self.assertIn('active) status_process_current "$status" || continue;', status)
        self.assertIn('prepared) status_process_current "$status" || continue;', status)
        self.assertIn('failed) failed=$((failed + 1))', status)


if __name__ == "__main__":
    unittest.main()
