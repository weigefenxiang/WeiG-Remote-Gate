import { chromium } from 'playwright';

const PREF_KEY = 'remote-gate:plan-preferences:v1';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function triggerFor(selectId) {
  return selectId === 'endpoint-select' ? '#endpoint-picker-trigger' : `#${selectId}-picker-trigger`;
}

async function chooseEndpoint(page, selectId, value) {
  await page.locator(triggerFor(selectId)).click();
  await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card');
  await page.locator(`#endpoint-picker-layer .endpoint-option-card[data-value="${value}"]`).click();
  await page.waitForFunction(({selectId, value}) => document.querySelector(`#${selectId}`)?.value === value, {selectId, value});
}

async function waitForSelection(page, selectId, value, source) {
  await page.waitForFunction(({selectId, value, source}) => {
    const endpoint = document.querySelector(`#${selectId}`);
    return endpoint?.value === value && endpoint?.dataset.selectionSource === source;
  }, {selectId, value, source});
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
  await chooseEndpoint(page, 'endpoint-select', 'ep-wan-v6');
  await waitForSelection(page, 'endpoint-select', 'ep-wan-v6', 'manual');

  const saved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(saved.schema === 1, 'manual endpoint preference schema was not persisted');
  assert(saved.lastFamily === 'ipv6', `wrong persisted family ${saved.lastFamily}`);
  assert(saved.lastWireguard === 'WG_HOME', `wrong persisted WireGuard ${saved.lastWireguard}`);
  assert(saved.endpoints?.ipv6?.wireguard === 'WG_HOME', 'IPv6 preference lost WireGuard binding');
  assert(saved.endpoints?.ipv6?.selection?.value === 'ep-wan-v6', 'manual endpoint id was not persisted');
  assert(saved.endpoints?.ipv6?.selection?.wan === 'WAN', 'manual endpoint WAN fallback hint was not persisted');
  assert(saved.endpoints?.ipv6?.selection?.method === 'direct', 'manual endpoint method hint was not persisted');
  assert(!saved.endpoints?.dual, 'legacy Dual pair preference was persisted');
  assert(!JSON.stringify(saved).includes('fixture-csrf'), 'plan preference persisted CSRF data');
  assert(!JSON.stringify(saved).includes('112.96.156.107'), 'plan preference persisted client source data');

  activatePosts = 0;
  await page.reload({waitUntil: 'networkidle'});
  await waitForSelection(page, 'endpoint-select', 'ep-wan-v6', 'manual');
  assert(activatePosts === 0, `reload restored preference by posting Activate (${activatePosts})`);

  topology = 'changed';
  await page.reload({waitUntil: 'networkidle'});
  await waitForSelection(page, 'endpoint-select', 'ep-wan-v6-new', 'manual');
  const remapped = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(remapped.endpoints?.ipv6?.selection?.value === 'ep-wan-v6-new', 'WAN fallback did not refresh the persisted endpoint identity');
  assert(remapped.endpoints?.ipv6?.selection?.wan === 'WAN', 'WAN fallback changed the manual WAN intent');
  assert(remapped.endpoints?.ipv6?.selection?.method === 'direct', 'WAN fallback lost the Access method hint');
  assert(activatePosts === 0, `topology churn posted Activate (${activatePosts})`);

  topology = 'removed';
  await page.reload({waitUntil: 'networkidle'});
  await waitForSelection(page, 'endpoint-select', 'ep-wan2-v6', 'auto');
  const cleared = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(!cleared.endpoints?.ipv6, 'invalid manual endpoint preference was not cleared');
  assert(activatePosts === 0, `invalid preference fallback posted Activate (${activatePosts})`);

  topology = 'ambiguous';
  await page.reload({waitUntil: 'networkidle'});
  await page.locator('[data-family="ipv4"]').click();
  await chooseEndpoint(page, 'endpoint-select', 'ep-wan2-v4-mapped');
  await waitForSelection(page, 'endpoint-select', 'ep-wan2-v4-mapped', 'manual');
  const mappedSaved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(mappedSaved.endpoints?.ipv4?.selection?.wan === 'WAN2', 'Mapped preference lost its WAN fallback hint');
  assert(mappedSaved.endpoints?.ipv4?.selection?.method === 'mapped', 'Mapped preference did not persist its Access method');

  topology = 'ambiguous_changed';
  await page.reload({waitUntil: 'networkidle'});
  await waitForSelection(page, 'endpoint-select', 'ep-wan2-v4-mapped-new', 'manual');
  const mappedRemapped = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(mappedRemapped.endpoints?.ipv4?.selection?.value === 'ep-wan2-v4-mapped-new', 'same-WAN method-aware fallback did not refresh the Mapped endpoint id');
  assert(mappedRemapped.endpoints?.ipv4?.selection?.method === 'mapped', 'same-WAN method-aware fallback silently changed Access method');
  const singleRows = await page.evaluate(() => JSON.parse(document.querySelector('#endpoint-select')?.selectedOptions?.[0]?.dataset.pathRows || '[]'));
  assert(singleRows.length === 1 && singleRows[0]?.role === 'Mapped', `same-WAN fallback selected the wrong Access method: ${singleRows[0]?.role}`);
  assert(activatePosts === 0, `same-WAN method churn posted Activate (${activatePosts})`);

  await page.locator('[data-family="dual"]').click();
  await page.waitForFunction(() => document.querySelector('#family-segment .active')?.dataset.family === 'dual');
  await waitForSelection(page, 'endpoint-select', 'ep-wan2-v4-mapped-new', 'manual');
  await page.waitForFunction(() => document.querySelector('#access-ipv6-select')?.value === 'ep-wan2-v6');
  await chooseEndpoint(page, 'access-ipv6-select', 'ep-wan2-v6');
  await waitForSelection(page, 'access-ipv6-select', 'ep-wan2-v6', 'manual');

  const dualSaved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(dualSaved.lastFamily === 'dual', `Dual mode was not persisted (${dualSaved.lastFamily})`);
  assert(dualSaved.endpoints?.ipv4?.selection?.value === 'ep-wan2-v4-mapped-new', 'Dual lost the scalar IPv4 endpoint preference');
  assert(dualSaved.endpoints?.ipv4?.selection?.method === 'mapped', 'Dual lost the scalar IPv4 Mapped method');
  assert(dualSaved.endpoints?.ipv6?.selection?.value === 'ep-wan2-v6', 'Dual lost the scalar IPv6 endpoint preference');
  assert(dualSaved.endpoints?.ipv6?.selection?.method === 'direct', 'Dual lost the scalar IPv6 Direct method');
  assert(!dualSaved.endpoints?.dual, 'Dual persisted a pair/shadow preference object');

  topology = 'dual_changed';
  await page.reload({waitUntil: 'networkidle'});
  await page.waitForFunction(() => document.querySelector('#family-segment .active')?.dataset.family === 'dual');
  await waitForSelection(page, 'endpoint-select', 'ep-wan2-v4-mapped-next', 'manual');
  await waitForSelection(page, 'access-ipv6-select', 'ep-wan2-v6', 'manual');
  const dualRemapped = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}'), PREF_KEY);
  assert(dualRemapped.endpoints?.ipv4?.selection?.value === 'ep-wan2-v4-mapped-next', 'Dual scalar IPv4 fallback did not refresh the endpoint id');
  assert(dualRemapped.endpoints?.ipv4?.selection?.method === 'mapped', 'Dual scalar IPv4 fallback silently changed Access method');
  assert(dualRemapped.endpoints?.ipv6?.selection?.value === 'ep-wan2-v6', 'Dual scalar IPv6 preference was rewritten by IPv4 churn');
  const dualRows = await page.evaluate(() => ({
    v4: JSON.parse(document.querySelector('#endpoint-select')?.selectedOptions?.[0]?.dataset.pathRows || '[]'),
    v6: JSON.parse(document.querySelector('#access-ipv6-select')?.selectedOptions?.[0]?.dataset.pathRows || '[]'),
  }));
  assert(dualRows.v4.length === 1 && dualRows.v4[0]?.role === 'Mapped', `Dual IPv4 scalar fallback selected the wrong method: ${dualRows.v4[0]?.role}`);
  assert(dualRows.v6.length === 1 && dualRows.v6[0]?.role === 'Global Direct', `Dual IPv6 scalar fallback selected the wrong method: ${dualRows.v6[0]?.role}`);
  assert(activatePosts === 0, `Dual scalar method churn posted Activate (${activatePosts})`);

  console.log('Browser plan preference regression passed: scalar reload persistence, WAN+method churn, Dual per-family preservation, invalidation, and zero auto-Activate.');
  await page.close();
} finally {
  await browser.close();
}
