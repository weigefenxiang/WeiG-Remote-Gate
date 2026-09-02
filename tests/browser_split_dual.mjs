import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (error) => consoleErrors.push(String(error)));

  await page.route('**/api/v1/dashboard', async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.endpoints = payload.endpoints.filter((endpoint) => endpoint.id !== 'ep-wan2-v6');
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });

  await page.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await page.waitForSelector('[data-family="dual"]');
  await page.locator('[data-family="dual"]').click();

  const splitEndpoint = 'dual:ep-wan2-v4:ep-wan-v6';
  await page.waitForFunction((expected) => {
    const select = document.querySelector('#endpoint-select');
    return select?.value === expected
      && select.dataset.selectionConfirmed === '1'
      && select.dataset.selectionSource === 'auto';
  }, splitEndpoint);
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'dual');
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN2');
  await page.waitForFunction(() => document.querySelector('#egress-ipv6-select')?.value === 'WAN2');
  assert(!(await page.locator('#activate-button').isDisabled()), 'split-WAN Dual Access did not enable Activate');

  const state = await page.evaluate(() => ({
    family: document.querySelector('#family-segment .active')?.dataset.family,
    endpoint: document.querySelector('#endpoint-select')?.value,
    endpointSource: document.querySelector('#endpoint-select')?.dataset.selectionSource,
    egressMode: document.querySelector('#egress-mode-segment .active')?.dataset.egressMode,
    egress4: document.querySelector('#egress-ipv4-select')?.value,
    egress6: document.querySelector('#egress-ipv6-select')?.value,
  }));
  assert(state.family === 'dual', `split-WAN Dual family changed unexpectedly (${state.family})`);
  assert(state.endpoint === splitEndpoint, `wrong split-WAN Dual endpoint (${state.endpoint})`);
  assert(state.endpointSource === 'auto', `split-WAN Dual endpoint was not automatic (${state.endpointSource})`);
  assert(state.egressMode === 'dual', `Internet Exit mode did not remain Dual (${state.egressMode})`);
  assert(state.egress4 === 'WAN2' && state.egress6 === 'WAN2', `Internet Exit must prefer the best shared dual-capable WAN independently of split Access (${state.egress4}/${state.egress6})`);

  const requestPromise = page.waitForRequest((request) =>
    request.url().endsWith('/api/v1/gate/activate') && request.method() === 'POST'
  );
  await page.locator('#activate-button').click();
  const body = (await requestPromise).postDataJSON();

  assert(JSON.stringify(body.families) === JSON.stringify(['ipv4', 'ipv6']), 'split Dual family list is incorrect');
  assert(body.endpoint_ids?.ipv4 === 'ep-wan2-v4', `split Dual IPv4 endpoint is incorrect (${body.endpoint_ids?.ipv4})`);
  assert(body.endpoint_ids?.ipv6 === 'ep-wan-v6', `split Dual IPv6 endpoint is incorrect (${body.endpoint_ids?.ipv6})`);
  assert(body.egress_mode === 'dual', `split Dual egress mode is incorrect (${body.egress_mode})`);
  assert(body.egress_wan === 'WAN2', `same-WAN Dual Internet Exit should expose the shared legacy WAN (${body.egress_wan})`);
  assert(body.egress_wans?.ipv4 === 'WAN2', `Dual IPv4 exit is incorrect (${body.egress_wans?.ipv4})`);
  assert(body.egress_wans?.ipv6 === 'WAN2', `Dual IPv6 exit is incorrect (${body.egress_wans?.ipv6})`);
  assert(!('source_ip' in body) && !('address' in body), 'split Dual request included a browser source address');
  assert(consoleErrors.length === 0, `split Dual browser console errors: ${consoleErrors.join(' | ')}`);

  await page.unrouteAll({behavior: 'ignoreErrors'});
  await page.close();
  console.log('Split-WAN Dual Access browser regression passed with independent shared-WAN Dual Internet Exit default.');
} finally {
  await browser.close();
}
