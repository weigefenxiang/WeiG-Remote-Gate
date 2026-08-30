# VPS installation

Requirements:
- Debian/Ubuntu style system with systemd
- Python 3
- OpenSSL
- curl

Install from a checkout:

```bash
sudo bash server/install.sh
```

Or download the installer from the repository and run it as root.

The installer creates:
- `/etc/remote-gate`
- `/var/lib/remote-gate`
- `/usr/local/lib/remote-gate`
- `remote-gate.service`
- a random `WRITE_TOKEN`

The service must listen only on:

```text
127.0.0.1:29444
```

Expose that localhost service through Cloudflare Tunnel.

Do not publish `WRITE_TOKEN`.
