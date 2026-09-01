from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "openwrt" / "remote-gate-mapping.sh"


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


if __name__ == "__main__":
    unittest.main()
