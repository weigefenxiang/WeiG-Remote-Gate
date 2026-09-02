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

function addMappedWan2Endpoint(payload, id, externalPort) {
  const direct = payload.endpoints.find((item) => item?.id === 'ep-wan2-v4');
  if (!direct) throw new Error('fixture is missing ep-wan2-v4');
  payload.endpoints.push({
    ...direct,
    id,
    reachability: 'mapped',
    access_method: 'mapped',
    provider: 'mapping_fixture',
    external_port: externalPort,
  });
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
    } else if (topology === 'ambiguous') {
      addMappedWan2Endpoint(payload, 'ep-wan2-v4-mapped', 62000);
    } else if (topology === 'ambiguous_changed') {
      addMappedWan2Endpoint(payload, 'ep-wan2-v4-mapped-new', 62001);
    } else if (topology === 'dual_changed') {
      addMappedWan2Endpoint(payload, 'ep-wan2-v4-mapped-next', 62002);
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
  assert(saved.endpoints?.ipv6?.selection?.method === 'direct', 'manual endpoint method hint was not persisted');
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
  assert(remapped.endpoints?.ipv6?.selection?.method === 'direct', 'WAN fallback lost the Access method hint');
  assert(activatePosts === 0, `topology churn posted Activate (${activatePosts})`);

  topology = 'removed';
  await page.reload({waitUntil: 'networkidle'});
  await waitForSelection(page, 'ipv6', 'ep-wan2-v6', 'auto');
  const cleared = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(!cleared.endpoints?.ipv6, 'invalid manual endpoint preference was not cleared');
  assert(activatePosts === 0, `invalid preference fallback posted Activate (${activatePosts})`);

  topology = 'ambiguous';
  await page.reload({waitUntil: 'networkidle'});
  await page.locator('[data-family="ipv4"]').click();
  await chooseEndpoint(page, 'ep-wan2-v4-mapped');
  await waitForSelection(page, 'ipv4', 'ep-wan2-v4-mapped', 'manual');
  const mappedSaved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(mappedSaved.endpoints?.ipv4?.selection?.wan === 'WAN2', 'Mapped preference lost its WAN fallback hint');
  assert(mappedSaved.endpoints?.ipv4?.selection?.method === 'mapped', 'Mapped preference did not persist its Access method');

  topology = 'ambiguous_changed';
  await page.reload({waitUntil: 'networkidle'});
  await waitForSelection(page, 'ipv4', 'ep-wan2-v4-mapped-new', 'manual');
  const mappedRemapped = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(mappedRemapped.endpoints?.ipv4?.selection?.value === 'ep-wan2-v4-mapped-new', 'same-WAN method-aware fallback did not refresh the Mapped endpoint id');
  assert(mappedRemapped.endpoints?.ipv4?.selection?.method === 'mapped', 'same-WAN method-aware fallback silently changed Access method');
  assert(document !== undefined, 'browser context unexpectedly unavailable');
  const singleRows = await page.evaluate(() => JSON.parse(document.querySelector('#endpoint-select')?.selectedOptions?.[0]?.dataset.pathRows || '[]'));
  assert(singleRows[0]?.role === 'Mapped', `same-WAN fallback selected the wrong Access method: ${singleRows[0]?.role}`);
  assert(activatePosts === 0, `same-WAN method churn posted Activate (${activatePosts})`);

  await page.locator('[data-family="dual"]').click();
  await page.waitForFunction(() => document.querySelector('#family-segment .active')?.dataset.family === 'dual');
  const mappedDual = await page.evaluate(() => {
    const options = [...(document.querySelector('#endpoint-select')?.options || [])];
    return options.find((option) => option.dataset.ipv4EndpointId === 'ep-wan2-v4-mapped-new' && option.dataset.ipv6EndpointId === 'ep-wan2-v6')?.value || '';
  });
  assert(mappedDual, 'fixture did not produce the expected Mapped + IPv6 Dual pair');
  await chooseEndpoint(page, mappedDual);
  await waitForSelection(page, 'dual', mappedDual, 'manual');
  const dualSaved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(dualSaved.endpoints?.dual?.selection?.wan4 === 'WAN2' && dualSaved.endpoints?.dual?.selection?.wan6 === 'WAN2', 'Dual preference lost WAN identity');
  assert(dualSaved.endpoints?.dual?.selection?.method4 === 'mapped', 'Dual preference lost IPv4 Mapped method');
  assert(dualSaved.endpoints?.dual?.selection?.method6 === 'direct', 'Dual preference lost IPv6 Direct method');

  topology = 'dual_changed';
  await page.reload({waitUntil: 'networkidle'});
  const mappedDualNext = 'dual:ep-wan2-v4-mapped-next:ep-wan2-v6';
  await waitForSelection(page, 'dual', mappedDualNext, 'manual');
  const dualRemapped = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(dualRemapped.endpoints?.dual?.selection?.value === mappedDualNext, 'Dual method-aware fallback did not refresh the constituent endpoint id');
  assert(dualRemapped.endpoints?.dual?.selection?.method4 === 'mapped', 'Dual method-aware fallback silently changed IPv4 Access method');
  assert(dualRemapped.endpoints?.dual?.selection?.method6 === 'direct', 'Dual method-aware fallback silently changed IPv6 Access method');
  const dualRows = await page.evaluate(() => JSON.parse(document.querySelector('#endpoint-select')?.selectedOptions?.[0]?.dataset.pathRows || '[]'));
  assert(dualRows[0]?.role === 'Mapped' && dualRows[1]?.role === 'Global Direct', `Dual fallback selected the wrong methods: ${dualRows.map((row) => row.role).join(' + ')}`);
  assert(activatePosts === 0, `Dual method churn posted Activate (${activatePosts})`);

  console.log('Browser plan preference regression passed: reload persistence, WAN+method churn, Dual method preservation, invalidation, and zero auto-Activate.');
  await page.close();
} finally {
  await browser.close();
}
