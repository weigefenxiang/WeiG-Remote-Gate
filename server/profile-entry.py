#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_PATH = Path(__file__).with_name("remote-gate.py")
SPEC = importlib.util.spec_from_file_location("remote_gate_base", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load Remote Gate base server")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

from app.client_profiles import (  # noqa: E402
    accept_profile_result,
    consume_public_token,
    create_public_token,
    queue_profile_create,
    queue_profile_revoke,
    render_format,
    result_view,
    sanitize_agent_profiles,
)
from app.client_sources import agent_status_is_fresh  # noqa: E402
from app.gate import GateError  # noqa: E402

STORE = base.STORE
SETTINGS = base.SETTINGS

PROFILE_CSS = r'''
.profile-launch-row{display:flex;justify-content:flex-end;margin-top:var(--space-3)}
.profile-launch{min-height:44px;padding:9px 14px;border:1px solid var(--hairline-strong);border-radius:var(--radius-sm);background:var(--surface-raised);color:var(--ink);box-shadow:var(--elevation-control-rest),var(--highlight-control);font:inherit;font-weight:700;cursor:pointer;transition:transform .14s ease,box-shadow .14s ease,border-color .14s ease}
.profile-launch:hover{border-color:var(--border-hover);transform:translateY(-1px);box-shadow:var(--elevation-control-hover),var(--highlight-control)}
.profile-layer{position:fixed;inset:0;z-index:1200;display:none;align-items:center;justify-content:center;padding:20px;background:rgba(0,0,0,.48);backdrop-filter:blur(8px)}
.profile-layer.open{display:flex}.profile-dialog{width:min(760px,100%);max-height:min(88vh,860px);overflow:auto;border:1px solid var(--hairline-strong);border-radius:var(--radius-lg);background:var(--surface-2);box-shadow:var(--depth-z4),var(--rim-light);padding:22px;color:var(--ink)}
.profile-dialog-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}.profile-dialog-head h2{margin:0;font-size:var(--type-card)}.profile-dialog-head p{margin:5px 0 0;color:var(--ink-muted);font-size:var(--type-label);line-height:1.45}.profile-close{min-width:44px;min-height:44px;border:0;border-radius:var(--radius-sm);background:transparent;color:var(--ink-muted);font-size:24px;cursor:pointer}.profile-close:hover{background:var(--surface-recessed);color:var(--ink)}
.profile-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.profile-field{display:grid;gap:6px;min-width:0}.profile-field.full{grid-column:1/-1}.profile-field label,.profile-label{font-size:var(--type-label);font-weight:700;color:var(--ink-muted)}.profile-field input,.profile-field select{width:100%;box-sizing:border-box;min-height:46px;border:1px solid var(--hairline-strong);border-radius:var(--radius-sm);background:var(--surface-recessed);color:var(--ink);padding:8px 10px;font:inherit}.profile-field input:focus-visible,.profile-field select:focus-visible,.profile-button:focus-visible,.profile-launch:focus-visible,.profile-close:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
.profile-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.profile-button{min-height:44px;border-radius:var(--radius-sm);border:1px solid var(--hairline-strong);padding:8px 12px;background:var(--surface-raised);color:var(--ink);box-shadow:var(--elevation-control-rest),var(--highlight-control);font:inherit;font-weight:700;cursor:pointer}.profile-button:hover{border-color:var(--border-hover)}.profile-button.primary{background:var(--primary);border-color:var(--primary);color:#fff}.profile-button.primary:hover{background:var(--primary-hover)}.profile-button.danger{color:var(--danger)}.profile-button:disabled{opacity:.48;cursor:not-allowed}
.profile-note{margin-top:12px;padding:10px 12px;border-radius:var(--radius-sm);background:var(--surface-recessed);color:var(--ink-muted);font-size:var(--type-label);line-height:1.5}.profile-note.warning{border:1px solid color-mix(in srgb,var(--warning) 45%,transparent)}.profile-list{display:grid;gap:8px;margin-top:18px}.profile-item{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px;border:1px solid var(--hairline);border-radius:var(--radius-sm);background:var(--surface-1)}.profile-item-main{min-width:0}.profile-item-name{font-weight:800}.profile-item-meta{margin-top:3px;color:var(--ink-muted);font-size:var(--type-caption);overflow-wrap:anywhere}.profile-empty{color:var(--ink-muted);padding:14px 0;font-size:var(--type-body)}
.profile-export{display:none;margin-top:18px;padding:14px;border:1px solid var(--hairline-strong);border-radius:var(--radius-md);background:var(--surface-1)}.profile-export.open{display:block}.profile-export-tabs{display:flex;flex-wrap:wrap;gap:7px}.profile-export-tabs button.active{border-color:var(--border-active);box-shadow:0 0 0 1px var(--border-active),var(--elevation-control-rest)}.profile-qr-wrap{display:none;margin-top:14px;text-align:center}.profile-qr-wrap.open{display:block}.profile-qr{width:min(280px,80vw);height:auto;background:white;border-radius:var(--radius-sm);padding:8px}.profile-status{min-height:20px;margin-top:10px;color:var(--ink-muted);font-size:var(--type-label)}.profile-status.error{color:var(--danger)}
@media(max-width:640px){.profile-layer{padding:0;align-items:flex-end}.profile-dialog{width:100%;max-height:92vh;border-radius:var(--radius-lg) var(--radius-lg) 0 0;padding:18px;padding-bottom:max(18px,env(safe-area-inset-bottom))}.profile-grid{grid-template-columns:1fr}.profile-field.full{grid-column:auto}.profile-item{align-items:flex-start;flex-direction:column}.profile-item .profile-actions{margin-top:0}}
@media(prefers-reduced-motion:reduce){.profile-launch{transition:none}}
'''

PROFILE_JS = r'''
(() => {
  const q = (s, root=document) => root.querySelector(s);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let csrf = '', dashboard = null, commandId = '', activeFormat = 'wireguard', pollTimer = 0;

  function eligibleEndpoints(data) {
    return (Array.isArray(data?.endpoints) ? data.endpoints : []).filter((ep) =>
      ep && ep.service_type === 'wireguard' && ['direct','mapped'].includes(ep.reachability) &&
      ['direct','mapped'].includes(ep.access_method) && ep.external_address && Number(ep.external_port || ep.ingress_port || ep.service_port) > 0);
  }
  function endpointLabel(ep) {
    const fam = ep.family === 'ipv6' ? 'IPv6' : 'IPv4';
    const address = ep.family === 'ipv6' ? `[${ep.external_address}]` : ep.external_address;
    const port = ep.external_port || ep.ingress_port || ep.service_port;
    const role = ep.access_method === 'mapped' ? 'Mapped' : (ep.family === 'ipv6' ? 'Global Direct' : 'Direct');
    return `${fam} · ${ep.wan || 'WAN'} · ${role} · ${address}:${port}`;
  }
  function setStatus(text, error=false) {
    const el = q('#profile-status'); if (!el) return; el.textContent = text || ''; el.classList.toggle('error', error);
  }
  function build() {
    const card = q('[data-card-id="wireguard"]');
    if (!card || q('#profile-launch')) return;
    const row = document.createElement('div'); row.className = 'profile-launch-row';
    row.innerHTML = '<button id="profile-launch" class="profile-launch" type="button">Manage clients</button>';
    card.append(row);
    const layer = document.createElement('div'); layer.id = 'profile-layer'; layer.className = 'profile-layer'; layer.innerHTML = `
      <section class="profile-dialog" role="dialog" aria-modal="true" aria-labelledby="profile-title" tabindex="-1">
        <div class="profile-dialog-head"><div><h2 id="profile-title">Client Profiles</h2><p>Create and revoke Remote Gate-managed WireGuard peers. Creating a profile never opens the Access Gate.</p></div><button class="profile-close" type="button" aria-label="Close">×</button></div>
        <div class="profile-grid">
          <div class="profile-field"><label for="profile-name">Client name</label><input id="profile-name" maxlength="48" autocomplete="off" placeholder="Pixel 10"></div>
          <div class="profile-field"><label for="profile-route">Routing</label><select id="profile-route"><option value="home">Home networks only</option><option value="full">Full IPv4 tunnel</option></select></div>
          <div class="profile-field full"><label for="profile-endpoint">Access endpoint snapshot</label><select id="profile-endpoint"></select></div>
          <div class="profile-field"><label for="profile-keepalive">Persistent keepalive</label><select id="profile-keepalive"><option value="25">25 seconds</option><option value="0">Off</option></select></div>
        </div>
        <div class="profile-actions"><button id="profile-create" class="profile-button primary" type="button">Create profile</button></div>
        <div class="profile-note warning">The client private key is generated on OpenWrt and is available only during this one-time export window. Remote Gate does not persist it on the VPS. Save the configuration before closing or refreshing.</div>
        <div id="profile-status" class="profile-status" aria-live="polite"></div>
        <div id="profile-export" class="profile-export"><span class="profile-label">One-time export</span><div id="profile-format-tabs" class="profile-export-tabs profile-actions"></div><div class="profile-actions"><button id="profile-download" class="profile-button" type="button">Download</button><button id="profile-copy" class="profile-button" type="button">Copy</button><button id="profile-qr-button" class="profile-button" type="button">QR</button></div><div id="profile-qr-wrap" class="profile-qr-wrap"><img id="profile-qr" class="profile-qr" alt="Client profile QR code"></div></div>
        <div id="profile-list" class="profile-list"></div>
      </section>`;
    document.body.append(layer);
    q('#profile-launch').addEventListener('click', open);
    q('.profile-close', layer).addEventListener('click', close);
    layer.addEventListener('click', (e) => { if (e.target === layer) close(); });
    q('#profile-create').addEventListener('click', createProfile);
    q('#profile-download').addEventListener('click', downloadProfile);
    q('#profile-copy').addEventListener('click', copyProfile);
    q('#profile-qr-button').addEventListener('click', showQr);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && layer.classList.contains('open')) close(); });
  }
  async function fetchDashboard() {
    const r = await fetch('/api/v1/dashboard', {credentials:'same-origin', cache:'no-store'});
    if (!r.ok) throw new Error(`Dashboard HTTP ${r.status}`);
    dashboard = await r.json(); csrf = dashboard.csrf || '';
    const select = q('#profile-endpoint');
    const eps = eligibleEndpoints(dashboard); select.replaceChildren();
    for (const ep of eps) { const o=document.createElement('option'); o.value=ep.id; o.textContent=endpointLabel(ep); select.append(o); }
    select.disabled = !eps.length; q('#profile-create').disabled = !eps.length;
    renderProfiles(dashboard?.agent?.client_profiles || []);
  }
  function renderProfiles(items) {
    const host=q('#profile-list'); host.replaceChildren();
    const title=document.createElement('span'); title.className='profile-label'; title.textContent='Managed clients'; host.append(title);
    if (!Array.isArray(items) || !items.length) { const empty=document.createElement('div'); empty.className='profile-empty'; empty.textContent='No Remote Gate-managed client peers.'; host.append(empty); return; }
    for (const item of items) {
      const row=document.createElement('div'); row.className='profile-item';
      row.innerHTML=`<div class="profile-item-main"><div class="profile-item-name">${esc(item.name)}</div><div class="profile-item-meta">${esc(item.client_address)} · ${esc(item.wireguard)} · ${esc(item.endpoint_family)} ${esc(item.access_method)} · private key not stored</div></div><div class="profile-actions"><button class="profile-button danger" type="button">Revoke</button></div>`;
      q('button',row).addEventListener('click',()=>revokeProfile(item.id)); host.append(row);
    }
  }
  async function open() {
    q('#profile-layer').classList.add('open'); q('.profile-dialog').focus(); setStatus('Loading current OpenWrt profile state…');
    try { await fetchDashboard(); setStatus(''); } catch (e) { setStatus(String(e.message || e), true); }
  }
  function close() { q('#profile-layer')?.classList.remove('open'); q('#profile-qr-wrap')?.classList.remove('open'); q('#profile-launch')?.focus(); }
  async function apiPost(path, body) {
    const r=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});
    const payload=await r.json().catch(()=>({})); if(!r.ok) throw new Error(payload.error || `HTTP ${r.status}`); return payload;
  }
  async function createProfile() {
    const name=q('#profile-name').value.trim(), endpointId=q('#profile-endpoint').value;
    if (!name || !endpointId) { setStatus('Enter a client name and choose an endpoint.', true); return; }
    q('#profile-create').disabled=true; q('#profile-export').classList.remove('open'); commandId=''; setStatus('Creating managed WireGuard peer on OpenWrt…');
    try {
      const p=await apiPost('/api/v1/client-profiles/create',{name,endpoint_id:endpointId,route_mode:q('#profile-route').value,persistent_keepalive:Number(q('#profile-keepalive').value)});
      commandId=p.command_id; pollResult();
    } catch(e) { setStatus(String(e.message||e),true); q('#profile-create').disabled=false; }
  }
  async function pollResult() {
    if (!commandId) return;
    clearTimeout(pollTimer);
    try {
      const r=await fetch(`/api/v1/client-profiles/result?command_id=${encodeURIComponent(commandId)}`,{credentials:'same-origin',cache:'no-store'});
      const p=await r.json().catch(()=>({}));
      if (r.status===202) { pollTimer=setTimeout(pollResult,1000); return; }
      if (!r.ok) throw new Error(p.error || `HTTP ${r.status}`);
      if (p.state!=='ready') { pollTimer=setTimeout(pollResult,1000); return; }
      showExport(p.profile); setStatus('Profile created. Save the one-time configuration now.'); q('#profile-create').disabled=false; await fetchDashboard();
    } catch(e) { setStatus(String(e.message||e),true); q('#profile-create').disabled=false; }
  }
  function showExport(profile) {
    const formats=Array.isArray(profile?.formats)?profile.formats:['wireguard']; const tabs=q('#profile-format-tabs'); tabs.replaceChildren();
    if(!formats.includes(activeFormat)) activeFormat='wireguard';
    for(const fmt of formats){const b=document.createElement('button');b.type='button';b.className='profile-button';b.textContent=fmt==='netproxy-8.1.0'?'NetProxy 8.1.0':fmt;b.classList.toggle('active',fmt===activeFormat);b.addEventListener('click',()=>{activeFormat=fmt;showExport(profile);q('#profile-qr-wrap').classList.remove('open');});tabs.append(b)}
    q('#profile-export').classList.add('open'); q('#profile-qr-wrap').classList.remove('open');
  }
  function exportUrl(){return `/api/v1/client-profiles/export/${encodeURIComponent(commandId)}/${encodeURIComponent(activeFormat)}`}
  function downloadProfile(){if(!commandId)return;location.href=exportUrl()}
  async function copyProfile(){if(!commandId)return;try{const r=await fetch(exportUrl(),{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);await navigator.clipboard.writeText(await r.text());setStatus('Configuration copied. It contains the private key; protect your clipboard.')}catch(e){setStatus(String(e.message||e),true)}}
  async function showQr(){if(!commandId)return;const img=q('#profile-qr');const url=`/api/v1/client-profiles/qr/${encodeURIComponent(commandId)}/${encodeURIComponent(activeFormat)}?t=${Date.now()}`;q('#profile-qr-wrap').classList.add('open');img.onload=()=>setStatus(activeFormat==='wireguard'?'QR contains the WireGuard private key. Scan it only on the intended client.':'QR contains a one-time HTTPS configuration URL.');img.onerror=()=>{q('#profile-qr-wrap').classList.remove('open');setStatus('QR generation is unavailable on this VPS. Download or Copy remains available.',true)};img.src=url}
  async function revokeProfile(id){if(!confirm('Revoke this Remote Gate-managed WireGuard client?'))return;setStatus('Revoking managed peer…');try{await apiPost('/api/v1/client-profiles/revoke',{profile_id:id});await waitForProfileRemoval(id)}catch(e){setStatus(String(e.message||e),true)}}
  async function waitForProfileRemoval(id){for(let i=0;i<25;i++){await new Promise(r=>setTimeout(r,1000));try{await fetchDashboard();if(!(dashboard?.agent?.client_profiles||[]).some(x=>x.id===id)){setStatus('Client revoked.');return}}catch(_){}}setStatus('Revoke is queued; OpenWrt has not reported convergence yet.')}
  build();
})();
'''


def _profile_export_ttl() -> int:
    try:
        config = json.loads((SETTINGS.config_dir / "config.json").read_text(encoding="utf-8"))
        value = int(config.get("profile_export_ttl_seconds", 300))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 300
    return value if 60 <= value <= 1800 else 300


def _send_bytes(handler, status: int, body: bytes, content_type: str, *, filename: str = "") -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    if filename:
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.end_headers()
    handler.wfile.write(body)


def _qr_svg(content: bytes) -> bytes:
    binary = shutil.which("qrencode")
    if not binary:
        raise GateError("qrencode_unavailable")
    if len(content) > 12_000:
        raise GateError("profile_qr_too_large")
    process = subprocess.run(
        [binary, "-t", "SVG", "-m", "2", "-o", "-"],
        input=content,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    if process.returncode != 0 or b"<svg" not in process.stdout[:512]:
        raise GateError("profile_qr_failed")
    return process.stdout


class Handler(base.Handler):
    def _template(self, name: str, replacements: dict[str, str] | None = None) -> str:
        value = super()._template(name, replacements)
        if name == "dashboard.html":
            value = value.replace("</head>", '<link rel="stylesheet" href="/client-profiles.css">\n</head>')
            value = value.replace("</body>", '<script src="/client-profiles.js"></script>\n</body>')
        return value

    def _require_browser(self):
        if not self._host_ok():
            return None
        return self._require_session()

    def _profile_create_post(self) -> None:
        session = self._require_browser()
        if not session or not self._require_csrf(session):
            return
        if not agent_status_is_fresh(STORE.read("agent-status.json", {})):
            self._json(503, {"error": "agent_unavailable"})
            return
        try:
            data = self._read_json()
            command = queue_profile_create(
                STORE,
                name=data.get("name"),
                endpoint_id=data.get("endpoint_id"),
                route_mode=data.get("route_mode", "home"),
                persistent_keepalive=data.get("persistent_keepalive", 25),
            )
        except (GateError, ValueError, TypeError) as exc:
            code = str(exc)
            self._json(409 if code == "command_pending" else 400, {"error": code})
            return
        base._touch_operator_activity()
        STORE.append_activity({
            "type": "profile_create_requested",
            "profile_id": command["profile_id"],
            "wireguard": command["wireguard"],
            "endpoint_id": command["endpoint_id"],
            "route_mode": command["route_mode"],
        })
        self._json(202, {"command_id": command["id"], "profile_id": command["profile_id"], "state": "pending"})

    def _profile_revoke_post(self) -> None:
        session = self._require_browser()
        if not session or not self._require_csrf(session):
            return
        if not agent_status_is_fresh(STORE.read("agent-status.json", {})):
            self._json(503, {"error": "agent_unavailable"})
            return
        try:
            data = self._read_json()
            command = queue_profile_revoke(STORE, data.get("profile_id"))
        except (GateError, ValueError, TypeError) as exc:
            code = str(exc)
            self._json(409 if code == "command_pending" else 400, {"error": code})
            return
        base._touch_operator_activity()
        STORE.append_activity({"type": "profile_revoke_requested", "profile_id": command["profile_id"]})
        self._json(202, {"command_id": command["id"], "profile_id": command["profile_id"], "state": "pending"})

    def _profile_result_post(self) -> None:
        if not self._host_ok() or not self._require_agent():
            return
        try:
            data = self._read_json()
            accept_profile_result(STORE, data, ttl_seconds=_profile_export_ttl())
        except (GateError, ValueError, TypeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        self._empty(204)

    def _profiles_status_post(self) -> None:
        if not self._host_ok() or not self._require_agent():
            return
        try:
            data = self._read_json()
            clean = sanitize_agent_profiles(data.get("client_profiles", []))
        except (ValueError, TypeError):
            self._json(400, {"error": "invalid_profiles_status"})
            return
        status = STORE.read("agent-status.json", {})
        if not isinstance(status, dict):
            status = {}
        status["client_profiles"] = clean
        STORE.write("agent-status.json", status)
        self._empty(204)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/client-profiles.css":
            if not self._host_ok():
                return
            _send_bytes(self, 200, PROFILE_CSS.encode("utf-8"), "text/css; charset=utf-8")
            return
        if path == "/client-profiles.js":
            if not self._host_ok():
                return
            _send_bytes(self, 200, PROFILE_JS.encode("utf-8"), "application/javascript; charset=utf-8")
            return
        if path.startswith("/p/"):
            if not self._host_ok():
                return
            token = path[len("/p/"):]
            try:
                content_type, filename, body = consume_public_token(token)
            except GateError:
                self._json(410, {"error": "profile_share_expired"})
                return
            _send_bytes(self, 200, body, content_type, filename=filename)
            return
        if path == "/api/v1/client-profiles/result":
            if not self._require_browser():
                return
            command_id = parse_qs(parsed.query).get("command_id", [""])[0]
            try:
                result = result_view(command_id)
            except GateError as exc:
                self._json(400, {"error": str(exc)})
                return
            if result is None:
                self._json(202, {"state": "pending"})
            else:
                self._json(200, {"state": "ready", "profile": result})
            return
        if path.startswith("/api/v1/client-profiles/export/"):
            if not self._require_browser():
                return
            parts = path.split("/")
            if len(parts) != 7:
                self._json(404, {"error": "not_found"})
                return
            try:
                content_type, filename, body = render_format(parts[5], parts[6])
            except GateError as exc:
                self._json(410, {"error": str(exc)})
                return
            _send_bytes(self, 200, body, content_type, filename=filename)
            return
        if path.startswith("/api/v1/client-profiles/qr/"):
            if not self._require_browser():
                return
            parts = path.split("/")
            if len(parts) != 7:
                self._json(404, {"error": "not_found"})
                return
            command_id, format_name = parts[5], parts[6]
            try:
                if format_name == "wireguard":
                    _, _, content = render_format(command_id, format_name)
                else:
                    share = create_public_token(
                        command_id,
                        format_name,
                        ttl_seconds=_profile_export_ttl(),
                        public_base=f"https://{SETTINGS.public_hostname}",
                    )
                    content = share["url"].encode("utf-8")
                svg = _qr_svg(content)
            except GateError as exc:
                self._json(503 if str(exc) == "qrencode_unavailable" else 400, {"error": str(exc)})
                return
            _send_bytes(self, 200, svg, "image/svg+xml; charset=utf-8")
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/v1/client-profiles/create":
            self._profile_create_post()
            return
        if path == "/api/v1/client-profiles/revoke":
            self._profile_revoke_post()
            return
        if path == "/api/v1/agent/profile-result":
            self._profile_result_post()
            return
        if path == "/api/v1/agent/profiles-status":
            self._profiles_status_post()
            return
        super().do_POST()


def run() -> None:
    server = base.ThreadingHTTPServer((SETTINGS.bind_host, SETTINGS.bind_port), Handler)
    print(f"WeiG-Remote-Gate listening on {SETTINGS.bind_host}:{SETTINGS.bind_port} for {SETTINGS.public_hostname}")
    server.serve_forever()


if __name__ == "__main__":
    run()
