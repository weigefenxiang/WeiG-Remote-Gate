import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function selectExitMode(page, mode) {
  await page.locator(`#egress-mode-segment [data-egress-mode="${mode}"]`).click();
  await page.waitForFunction((value) => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === value, mode);
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
    if (topology === 'wan-v4-down') {
      const wan = payload.inventory?.wans?.find((item) => item?.name === 'WAN');
      if (wan) wan.default_route_v4 = false;
    }
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });

  await page.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'ipv4');
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN2');

  await page.selectOption('#egress-ipv4-select', 'WAN');
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN');
  await page.waitForTimeout(100);
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN', 'manual IPv4 Internet Exit was overwritten by its own render');

  await page.locator('[data-family="ipv6"]').click();
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'ipv6');
  await page.waitForFunction(() => document.querySelector('#egress-ipv6-select')?.value === 'WAN2');
  await page.locator('[data-family="ipv4"]').click();
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'ipv4');
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN');
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN', 'manual IPv4 Internet Exit was not restored after Access-family switching');

  await selectExitMode(page, 'dual');
  await page.waitForFunction(() => !document.querySelector('#egress-ipv4-select')?.closest('.field')?.hidden && !document.querySelector('#egress-ipv6-select')?.closest('.field')?.hidden);
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN', 'Dual did not retain the explicit IPv4 WAN scalar');
  assert(await page.locator('#egress-ipv6-select').inputValue() === 'WAN2', 'Dual did not use the independently recommended IPv6 WAN scalar');

  await selectExitMode(page, 'ipv4');
  topology = 'wan-v4-down';
  await page.evaluate(() => window.RemoteGateApp?.refresh?.());
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN2');
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN2', 'invalid manual Internet Exit did not fail back to a current WAN');

  topology = 'normal';
  await page.evaluate(() => window.RemoteGateApp?.refresh?.());
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN2');
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN2', 'invalidated manual Internet Exit reappeared after topology recovery');
  assert(activatePosts === 0, `manual Internet Exit state changes posted Activate (${activatePosts})`);

  console.log('Browser manual Internet Exit regression passed: mode-first selection, independent family WAN scalars, invalidation, and zero auto-Activate.');
  await page.close();
} finally {
  await browser.close();
}
