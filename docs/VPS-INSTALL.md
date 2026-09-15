# VPS installation

Requirements:
- Debian/Ubuntu style system with systemd
- Python 3
- OpenSSL
- curl
- `apt-get` access to the distribution package repositories

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

The installer and updater require `qrencode` for Client Profile QR export. If the binary is missing, they install the Debian/Ubuntu `qrencode` package before changing the Remote Gate runtime. If package installation cannot complete, installation/update stops before replacing the service so the UI is not knowingly deployed with a broken QR action.

The service must listen only on:

```text
127.0.0.1:29444
```

Expose that localhost service through Cloudflare Tunnel.

Do not publish `WRITE_TOKEN`.
