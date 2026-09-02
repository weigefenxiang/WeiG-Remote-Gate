import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function addAltWireGuard(payload) {
  const baseWg = payload.agent?.wireguard?.find((item) => item?.name === 'WG_HOME');
  if (!baseWg) throw new Error('fixture is missing WG_HOME');
  payload.agent.wireguard = [baseWg, {...baseWg, name: 'WG_ALT', listen_port: 41194}];
  const altEndpoints = payload.endpoints
    .filter((item) => item?.wireguard === 'WG_HOME')
    .map((item) => ({
      ...item,
      id: `${item.id}-alt`,
      wireguard: 'WG_ALT',
      service_id: 'wg.WG_ALT',
      external_port: item.reachability === 'mapped' ? item.external_port : 41194,
      ingress_port: item.reachability === 'mapped' ? item.ingress_port : 41194,
      local_port: item.reachability === 'mapped' ? item.local_port : 41194,
      service_port: 41194,
    }));
  payload.endpoints.push(...altEndpoints);
}

function setIpv4GateOpen(payload) {
  const source = payload.client_sources?.ipv4?.address;
  if (!source) throw new Error('fixture is missing IPv4 client source');
  const family = {
    active: true,
    family: 'ipv4',
    scope: 'wg',
    source_ip: source,
    source_kind: 'web_candidate',
    device: 'pppoe-WAN2',
    ingress_port: 51820,
    wg_port: 51820,
    expires_in: 300,
    source_count: 1,
    authorized_sources: [source],
    authorizations: [{source_ip: source, source_kind: 'web_candidate', expires_in: 300}],
  };
  payload.agent.fresh = true;
  payload.agent.firewall = {
    ...payload.agent.firewall,
    active: true,
    family: 'ipv4',
    scope: 'wg',
    source_ip: source,
    device: 'pppoe-WAN2',
    ingress_port: 51820,
    wg_port: 51820,
    expires_in: 300,
    families: {
      ipv4: family,
      ipv6: {
        active: false,
        family: 'ipv6',
        scope: '',
        source_ip: '',
        device: '',
        ingress_port: 0,
        wg_port: 0,
        expires_in: 0,
        source_count: 0,
        authorized_sources: [],
        authorizations: [],
      },
    },
  };
}

const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  let activatePosts = 0;

  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/gate/activate') activatePosts += 1;
  });

  await page.route('**/api/v1/dashboard', async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    addAltWireGuard(payload);
    setIpv4GateOpen(payload);
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });

  await page.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await page.waitForSelector('#endpoint-picker-trigger');
  await page.locator('[data-family="ipv4"]').click();
  await page.waitForFunction(() => document.querySelector('#wg-select')?.value === 'WG_HOME');
  await page.waitForFunction(() => document.querySelector('#endpoint-select')?.value === 'ep-wan2-v4');
  await page.waitForFunction(() => document.querySelector('#gate-state-badge')?.textContent === 'AUTHORIZED');

  assert(await page.locator('#wg-select').isVisible(), 'two WireGuard services should expose the service selector');
  assert(!(await page.locator('#close-button').evaluate((node) => node.classList.contains('hidden'))), 'matching active profile should expose Close');
  assert(await page.locator('#activate-button').evaluate((node) => node.classList.contains('hidden')), 'matching active profile must hide Activate');

  await page.locator('[data-scope="wg_ping"]').click();
  await page.waitForFunction(() => document.querySelector('#gate-state')?.textContent === 'OPEN · OTHER ACCESS PATH');
  assert((await page.locator('#gate-state-badge').textContent()) === 'OPEN ELSEWHERE', 'scope mismatch should be shown as an active profile elsewhere');
  assert(!(await page.locator('#close-button').evaluate((node) => node.classList.contains('hidden'))), 'scope mismatch must keep Close available');
  assert(await page.locator('#activate-button').evaluate((node) => node.classList.contains('hidden')), 'scope mismatch must not offer Activate');
  assert((await page.locator('#gate-orb').getAttribute('aria-label')) === 'Close access now', 'orb must close a conflicting active profile');

  await page.locator('[data-scope="wg"]').click();
  await page.waitForFunction(() => document.querySelector('#gate-state-badge')?.textContent === 'AUTHORIZED');

  await page.locator('#wg-select').selectOption('WG_ALT');
  await page.waitForFunction(() => document.querySelector('#wg-select')?.value === 'WG_ALT');
  await page.waitForFunction(() => document.querySelector('#endpoint-select')?.value === 'ep-wan2-v4-alt');
  await page.waitForFunction(() => document.querySelector('#gate-state')?.textContent === 'OPEN · OTHER ACCESS PATH');
  assert((await page.locator('#gate-state-badge').textContent()) === 'OPEN ELSEWHERE', 'different WireGuard ingress must not inherit OPEN state from the authorized source');
  assert(!(await page.locator('#close-button').evaluate((node) => node.classList.contains('hidden'))), 'different WireGuard ingress must keep Close available');
  assert(await page.locator('#activate-button').evaluate((node) => node.classList.contains('hidden')), 'different WireGuard ingress must block replacement Activate');
  assert((await page.locator('#gate-orb').getAttribute('aria-label')) === 'Close access now', 'orb must close instead of activating across an active profile conflict');

  await page.locator('#wg-select').selectOption('WG_HOME');
  await page.waitForFunction(() => document.querySelector('#wg-select')?.value === 'WG_HOME');
  await page.waitForFunction(() => document.querySelector('#endpoint-select')?.value === 'ep-wan2-v4');
  await page.waitForFunction(() => document.querySelector('#gate-state-badge')?.textContent === 'AUTHORIZED');
  assert(activatePosts === 0, `profile selection changes posted Activate (${activatePosts})`);

  console.log('Browser Gate profile binding regression passed: OPEN requires source plus device/ingress/scope identity, conflicts stay close-only, and selection changes never auto-Activate.');
  await page.close();
} finally {
  await browser.close();
}
