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

  await page.waitForFunction(() => {
    const v4 = document.querySelector('#endpoint-select');
    const v6 = document.querySelector('#access-ipv6-select');
    return v4?.value === 'ep-wan2-v4' && v4.dataset.selectionConfirmed === '1' && v4.dataset.selectionSource === 'auto'
      && v6?.value === 'ep-wan-v6' && v6.dataset.selectionConfirmed === '1' && v6.dataset.selectionSource === 'auto';
  });
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'dual');
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN2');
  await page.waitForFunction(() => document.querySelector('#egress-ipv6-select')?.value === 'WAN2');
  assert(!(await page.locator('#activate-button').isDisabled()), 'split-WAN Dual Access did not enable Activate');

  const state = await page.evaluate(() => ({
    family: document.querySelector('#family-segment .active')?.dataset.family,
    endpoint4: document.querySelector('#endpoint-select')?.value,
    source4: document.querySelector('#endpoint-select')?.dataset.selectionSource,
    endpoint6: document.querySelector('#access-ipv6-select')?.value,
    source6: document.querySelector('#access-ipv6-select')?.dataset.selectionSource,
    pairIds: [...document.querySelectorAll('#endpoint-select option, #access-ipv6-select option')].map((option) => option.value).filter((value) => String(value).startsWith('dual:')),
    egressMode: document.querySelector('#egress-mode-segment .active')?.dataset.egressMode,
    egress4: document.querySelector('#egress-ipv4-select')?.value,
    egress6: document.querySelector('#egress-ipv6-select')?.value,
  }));
  assert(state.family === 'dual', `split-WAN Dual family changed unexpectedly (${state.family})`);
  assert(state.endpoint4 === 'ep-wan2-v4' && state.endpoint6 === 'ep-wan-v6', `wrong split-WAN scalar endpoints (${state.endpoint4}/${state.endpoint6})`);
  assert(state.source4 === 'auto' && state.source6 === 'auto', `split-WAN Dual selectors were not automatic (${state.source4}/${state.source6})`);
  assert(state.pairIds.length === 0, `split-WAN Dual still generated pair ids (${state.pairIds.join(',')})`);
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
  console.log('Split-WAN Dual Access browser regression passed with two independent Access selectors and independent shared-WAN Dual Internet Exit default.');
} finally {
  await browser.close();
}
