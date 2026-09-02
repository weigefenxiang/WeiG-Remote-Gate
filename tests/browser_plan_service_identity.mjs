import { chromium } from 'playwright';

const PREF_KEY = 'remote-gate:plan-preferences:v1';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function chooseEndpoint(page, value) {
  await page.locator('#endpoint-picker-trigger').click();
  await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card');
  await page.locator(`#endpoint-picker-layer .endpoint-option-card[data-value="${value}"]`).click();
  await page.waitForFunction((expected) => document.querySelector('#endpoint-select')?.value === expected, value);
}

function addAltWireGuard(payload, {only = false} = {}) {
  const baseWg = payload.agent?.wireguard?.find((item) => item?.name === 'WG_HOME');
  if (!baseWg) throw new Error('fixture is missing WG_HOME');
  const altWg = {...baseWg, name: 'WG_ALT', listen_port: 41194};
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
  if (only) {
    payload.agent.wireguard = [altWg];
    payload.endpoints = altEndpoints;
  } else {
    payload.agent.wireguard = [baseWg, altWg];
    payload.endpoints.push(...altEndpoints);
  }
}

const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  let topology = 'home';
  let activatePosts = 0;

  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/gate/activate') activatePosts += 1;
  });

  await page.route('**/api/v1/dashboard', async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (topology === 'both') addAltWireGuard(payload);
    if (topology === 'alt') addAltWireGuard(payload, {only: true});
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });

  await page.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await page.evaluate((key) => localStorage.removeItem(key), PREF_KEY);
  await page.reload({waitUntil: 'networkidle'});
  await page.waitForSelector('#endpoint-picker-trigger');

  assert(!(await page.locator('#wg-select').isVisible()), 'single WireGuard service should keep the redundant selector hidden');

  await page.locator('[data-family="ipv4"]').click();
  await chooseEndpoint(page, 'ep-wan2-v4');
  await page.waitForFunction(() => document.querySelector('#endpoint-select')?.dataset.selectionSource === 'manual');

  const saved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(saved.lastWireguard === 'WG_HOME', `wrong persisted WireGuard ${saved.lastWireguard}`);
  assert(saved.endpoints?.ipv4?.wireguard === 'WG_HOME', 'manual IPv4 preference lost its WireGuard binding');
  assert(saved.endpoints?.ipv4?.selection?.value === 'ep-wan2-v4', 'manual IPv4 endpoint was not persisted');

  activatePosts = 0;
  topology = 'both';
  await page.evaluate(() => window.RemoteGateApp.refresh());
  await page.waitForFunction(() => document.querySelectorAll('#wg-select option').length === 2);
  await page.waitForFunction(() => document.querySelector('#wg-select')?.value === 'WG_HOME');
  assert(await page.locator('#wg-select').isVisible(), 'multiple registered WireGuard services must expose a real service selector');
  await page.waitForFunction(() => document.querySelector('#endpoint-select')?.dataset.selectionSource === 'manual');

  await page.locator('#wg-select').selectOption('WG_ALT');
  await page.waitForFunction(() => document.querySelector('#wg-select')?.value === 'WG_ALT');
  await page.waitForFunction(() => {
    const endpoint = document.querySelector('#endpoint-select');
    return endpoint?.value === 'ep-wan2-v4-alt' && endpoint?.dataset.selectionSource === 'auto';
  });
  const afterExplicitSwitch = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(!afterExplicitSwitch.endpoints?.ipv4, 'WG_HOME manual endpoint preference migrated across an explicit switch to WG_ALT');

  await chooseEndpoint(page, 'ep-wan2-v4-alt');
  await page.waitForFunction(() => document.querySelector('#endpoint-select')?.dataset.selectionSource === 'manual');
  const altSaved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(altSaved.endpoints?.ipv4?.wireguard === 'WG_ALT', 'WG_ALT manual endpoint preference lost its service binding');

  topology = 'home';
  await page.evaluate(() => window.RemoteGateApp.refresh());
  await page.waitForFunction(() => document.querySelector('#wg-select')?.value === 'WG_HOME');
  await page.waitForFunction(() => {
    const endpoint = document.querySelector('#endpoint-select');
    return endpoint?.value === 'ep-wan2-v4' && endpoint?.dataset.selectionSource === 'auto';
  });
  assert(!(await page.locator('#wg-select').isVisible()), 'selector should become redundant and hidden again after WG_ALT disappears');
  const afterDisappear = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(!afterDisappear.endpoints?.ipv4, 'stale WG_ALT manual endpoint preference survived service disappearance');
  assert(activatePosts === 0, `WireGuard service selection/churn posted Activate (${activatePosts})`);

  console.log('Browser plan service identity regression passed: single-service hiding, multi-service selection, service-bound manual intent, churn fallback, and zero auto-Activate.');
  await page.close();
} finally {
  await browser.close();
}
