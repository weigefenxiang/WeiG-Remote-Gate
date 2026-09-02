import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
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
  await page.waitForFunction(() => document.querySelector('#egress-select')?.value === 'ipv4:WAN2');

  await page.selectOption('#egress-select', 'ipv4:WAN');
  await page.waitForFunction(() => document.querySelector('#egress-select')?.value === 'ipv4:WAN');
  await page.waitForTimeout(100);
  assert(await page.locator('#egress-select').inputValue() === 'ipv4:WAN', 'manual IPv4 Internet Exit was overwritten by its own render');

  await page.locator('[data-family="ipv6"]').click();
  await page.waitForFunction(() => document.querySelector('#egress-select')?.value === 'ipv6:WAN2');
  await page.locator('[data-family="ipv4"]').click();
  await page.waitForFunction(() => document.querySelector('#egress-select')?.value === 'ipv4:WAN');
  assert(await page.locator('#egress-select').inputValue() === 'ipv4:WAN', 'manual IPv4 Internet Exit was not restored after family switching');

  topology = 'wan-v4-down';
  await page.evaluate(() => window.RemoteGateApp?.refresh?.());
  await page.waitForFunction(() => document.querySelector('#egress-select')?.value === 'ipv4:WAN2');
  assert(await page.locator('#egress-select').inputValue() === 'ipv4:WAN2', 'invalid manual Internet Exit did not fail back to a current plan');

  topology = 'normal';
  await page.evaluate(() => window.RemoteGateApp?.refresh?.());
  await page.waitForFunction(() => document.querySelector('#egress-select')?.value === 'ipv4:WAN2');
  assert(await page.locator('#egress-select').inputValue() === 'ipv4:WAN2', 'invalidated manual Internet Exit reappeared after topology recovery');
  assert(activatePosts === 0, `manual Internet Exit state changes posted Activate (${activatePosts})`);

  console.log('Browser manual Internet Exit regression passed: immediate retention, per-family restore, invalidation, and zero auto-Activate.');
  await page.close();
} finally {
  await browser.close();
}
