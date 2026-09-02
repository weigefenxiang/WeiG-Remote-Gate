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

async function waitForSelection(page, family, value, source) {
  await page.waitForFunction(({family, value, source}) => {
    const activeFamily = document.querySelector('#family-segment .active')?.dataset.family;
    const endpoint = document.querySelector('#endpoint-select');
    return activeFamily === family && endpoint?.value === value && endpoint?.dataset.selectionSource === source;
  }, {family, value, source});
}

const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  let topology = 'normal';
  let activatePosts = 0;

  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/gate/activate') activatePosts += 1;
  });

  await page.route('**/api/v1/dashboard', async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (topology === 'changed') {
      const endpoint = payload.endpoints.find((item) => item?.id === 'ep-wan-v6');
      if (endpoint) {
        endpoint.id = 'ep-wan-v6-new';
        endpoint.external_address = '2409:8a55:1905:702e:f193:310e:cf14:50f1';
      }
    } else if (topology === 'removed') {
      payload.endpoints = payload.endpoints.filter((item) => !(item?.family === 'ipv6' && item?.wan === 'WAN'));
    }
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });

  await page.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await page.evaluate((key) => localStorage.removeItem(key), PREF_KEY);
  await page.reload({waitUntil: 'networkidle'});
  await page.waitForSelector('#endpoint-picker-trigger');

  await page.locator('[data-family="ipv6"]').click();
  await chooseEndpoint(page, 'ep-wan-v6');
  await waitForSelection(page, 'ipv6', 'ep-wan-v6', 'manual');

  const saved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(saved.schema === 1, 'manual endpoint preference schema was not persisted');
  assert(saved.lastFamily === 'ipv6', `wrong persisted family ${saved.lastFamily}`);
  assert(saved.lastWireguard === 'WG_HOME', `wrong persisted WireGuard ${saved.lastWireguard}`);
  assert(saved.endpoints?.ipv6?.wireguard === 'WG_HOME', 'IPv6 preference lost WireGuard binding');
  assert(saved.endpoints?.ipv6?.selection?.value === 'ep-wan-v6', 'manual endpoint id was not persisted');
  assert(saved.endpoints?.ipv6?.selection?.wan === 'WAN', 'manual endpoint WAN fallback hint was not persisted');
  assert(!JSON.stringify(saved).includes('fixture-csrf'), 'plan preference persisted CSRF data');
  assert(!JSON.stringify(saved).includes('112.96.156.107'), 'plan preference persisted client source data');

  activatePosts = 0;
  await page.reload({waitUntil: 'networkidle'});
  await waitForSelection(page, 'ipv6', 'ep-wan-v6', 'manual');
  assert(activatePosts === 0, `reload restored preference by posting Activate (${activatePosts})`);

  topology = 'changed';
  await page.reload({waitUntil: 'networkidle'});
  await waitForSelection(page, 'ipv6', 'ep-wan-v6-new', 'manual');
  const remapped = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(remapped.endpoints?.ipv6?.selection?.value === 'ep-wan-v6-new', 'WAN fallback did not refresh the persisted endpoint identity');
  assert(remapped.endpoints?.ipv6?.selection?.wan === 'WAN', 'WAN fallback changed the manual WAN intent');
  assert(activatePosts === 0, `topology churn posted Activate (${activatePosts})`);

  topology = 'removed';
  await page.reload({waitUntil: 'networkidle'});
  await waitForSelection(page, 'ipv6', 'ep-wan2-v6', 'auto');
  const cleared = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(!cleared.endpoints?.ipv6, 'invalid manual endpoint preference was not cleared');
  assert(activatePosts === 0, `invalid preference fallback posted Activate (${activatePosts})`);

  console.log('Browser plan preference regression passed: reload persistence, WAN fallback, invalidation, and zero auto-Activate.');
  await page.close();
} finally {
  await browser.close();
}
