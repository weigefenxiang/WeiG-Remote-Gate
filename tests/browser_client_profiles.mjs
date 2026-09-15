import fs from 'node:fs';
import { chromium } from 'playwright';

const source = fs.readFileSync('server/profile-entry.py', 'utf8');
function rawString(name) {
  const pattern = new RegExp(`${name} = r'''([\\s\\S]*?)'''`);
  const match = source.match(pattern);
  if (!match) throw new Error(`missing ${name}`);
  return match[1];
}
const css = rawString('PROFILE_CSS');
const js = rawString('PROFILE_JS');
if (/localStorage|sessionStorage/.test(js)) throw new Error('Client Profiles must not persist browser secrets/state in Web Storage');

const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage({viewport: {width: 1280, height: 900}});
  await page.setContent(`<!doctype html><html><head><style>
    :root{--space-3:12px;--hairline-strong:#ccc;--hairline:#ddd;--radius-sm:12px;--radius-md:16px;--radius-lg:22px;--surface-raised:#fff;--surface-recessed:#f4f4f4;--surface-2:#fff;--surface-1:#fafafa;--ink:#111;--ink-muted:#666;--primary:#5965e8;--primary-hover:#6874f2;--danger:#d84a4a;--warning:#d8871a;--border-hover:#8890ee;--border-active:#5965e8;--elevation-control-rest:none;--elevation-control-hover:none;--highlight-control:none;--depth-z4:none;--rim-light:none;--type-card:22px;--type-label:13px;--type-caption:12px;--type-body:15px}
    body{font-family:sans-serif}.workspace-card{padding:20px;border:1px solid #ddd;border-radius:16px}
    ${css}</style></head><body><article class="workspace-card" data-card-id="wireguard"><h2>WireGuard</h2></article></body></html>`);

  await page.evaluate(() => {
    window.fetch = async (input, init = {}) => {
      const url = String(input);
      if (url === '/api/v1/dashboard') {
        return new Response(JSON.stringify({
          csrf: 'csrf-test',
          endpoints: [{id:'ep_11111111111111111111', family:'ipv4', access_method:'direct', reachability:'direct', service_type:'wireguard', wireguard:'WG_HOME', wan:'WAN2', external_address:'198.51.100.18', external_port:51820}],
          agent: {client_profiles: [{id:'aaaaaaaaaaaaaaaaaaaaaaaa', name:'Existing', client_address:'10.66.66.3/32', wireguard:'WG_HOME', endpoint_family:'ipv4', access_method:'direct'}]}
        }), {status: 200, headers: {'Content-Type':'application/json'}});
      }
      if (url === '/api/v1/client-profiles/recent') {
        return new Response(JSON.stringify({
          recent: [{command_id:'dddddddddddddddddddddddddddddddd', profile:{id:'eeeeeeeeeeeeeeeeeeeeeeee',name:'Recovered',client_address:'10.66.66.4/32',wireguard:'WG_HOME',formats:['wireguard','flclash','netproxy-8.1.0','sing-box'],export_available:true,export_expires_at:Math.floor(Date.now()/1000)+240,created_at:Math.floor(Date.now()/1000)-30}}],
          history: [{profile_id:'eeeeeeeeeeeeeeeeeeeeeeee',name:'Recovered',client_address:'10.66.66.4/32',wireguard:'WG_HOME',endpoint_family:'ipv4',access_method:'direct',created_at:Math.floor(Date.now()/1000)-30}]
        }), {status:200, headers:{'Content-Type':'application/json'}});
      }
      if (url === '/api/v1/client-profiles/create' && init.method === 'POST') {
        const body = JSON.parse(init.body);
        if (body.endpoint_id !== 'ep_11111111111111111111') return new Response('{}', {status:400});
        return new Response(JSON.stringify({command_id:'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', profile_id:'cccccccccccccccccccccccc', state:'pending'}), {status:202, headers:{'Content-Type':'application/json'}});
      }
      if (url.startsWith('/api/v1/client-profiles/result?')) {
        return new Response(JSON.stringify({state:'ready', profile:{id:'cccccccccccccccccccccccc',name:'Pixel 10',client_address:'10.66.66.5/32',wireguard:'WG_HOME',formats:['wireguard','flclash','netproxy-8.1.0','sing-box'],export_available:true,export_expires_at:Math.floor(Date.now()/1000)+300}}), {status:200, headers:{'Content-Type':'application/json'}});
      }
      return new Response(JSON.stringify({error:`unexpected ${url}`}), {status:404, headers:{'Content-Type':'application/json'}});
    };
  });
  await page.addScriptTag({content: js});

  await page.getByRole('button', {name: 'Manage clients'}).click();
  await page.locator('#profile-layer .profile-dialog').waitFor({state:'visible'});
  const endpointText = await page.locator('#profile-endpoint option').textContent();
  if (!endpointText?.includes('WAN2') || !endpointText.includes('Direct')) throw new Error(`unexpected endpoint label: ${endpointText}`);
  await page.getByText('Existing', {exact:true}).waitFor();

  const recentButton = page.locator('#profile-recent-button');
  const count = await page.locator('#profile-recent-count').textContent();
  if (count !== '1') throw new Error(`recent result count should be 1, got ${count}`);
  await recentButton.click();
  await page.getByText('Recovered', {exact:true}).first().waitFor();
  await page.getByRole('button', {name:'Open export'}).click();
  await page.locator('#profile-export.open').waitFor({state:'visible'});

  await page.locator('#profile-name').fill('Pixel 10');
  await page.getByRole('button', {name:'Create profile'}).click();
  await page.locator('#profile-export.open').waitFor({state:'visible', timeout:5000});
  await page.getByRole('button', {name:'NetProxy 8.1.0'}).waitFor();
  const status = await page.locator('#profile-status').textContent();
  if (!status?.includes('Profile created')) throw new Error(`unexpected status: ${status}`);

  await page.setViewportSize({width: 390, height: 844});
  const dialog = page.locator('#profile-layer .profile-dialog');
  const radius = await dialog.evaluate((el) => getComputedStyle(el).borderTopLeftRadius);
  if (!radius || radius === '0px') throw new Error('mobile Client Profiles sheet lost rounded top edge');
  const bottom = await page.locator('#profile-layer').evaluate((el) => getComputedStyle(el).alignItems);
  if (bottom !== 'flex-end') throw new Error(`mobile sheet should align to bottom, got ${bottom}`);

  await page.evaluate(() => {
    const layer=document.querySelector('#profile-qr-layer');
    const img=document.querySelector('#profile-qr');
    layer.classList.add('open');
    img.src='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"><rect width="400" height="400" fill="white"/><rect x="32" y="32" width="336" height="336" fill="black"/></svg>';
  });
  await page.locator('#profile-qr').evaluate((img) => img.complete ? true : new Promise((resolve) => { img.onload=()=>resolve(true); }));
  const qrBox = await page.locator('#profile-qr').boundingBox();
  if (!qrBox) throw new Error('mobile QR is not visible');
  if (qrBox.x < 0 || qrBox.y < 0 || qrBox.x + qrBox.width > 390.5 || qrBox.y + qrBox.height > 844.5) {
    throw new Error(`mobile QR clipped outside viewport: ${JSON.stringify(qrBox)}`);
  }
  const qrDialogBox = await page.locator('#profile-qr-layer .profile-qr-dialog').boundingBox();
  if (!qrDialogBox || qrDialogBox.height > 844.5) throw new Error(`QR viewer exceeds dynamic viewport: ${JSON.stringify(qrDialogBox)}`);
  console.log('client profiles browser regression: PASS');
} finally {
  await browser.close();
}
