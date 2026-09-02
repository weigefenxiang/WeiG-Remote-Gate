import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function selectExitMode(page, mode) {
  await page.locator(`#egress-mode-segment [data-egress-mode="${mode}"]`).click();
  await page.waitForFunction((value) => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === value, mode);
}

async function assertExitPicker(page, family) {
  const opposite = family === 'ipv4' ? 'ipv6' : 'ipv4';
  const trigger = page.locator(`#egress-${family}-select-picker-trigger`);
  assert(await trigger.isVisible(), `${family} Internet Exit trigger is not visible`);
  await trigger.click();
  await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card');
  const snapshot = await page.evaluate(({family, opposite}) => {
    const cards = [...document.querySelectorAll('#endpoint-picker-layer .endpoint-option-card')];
    return {
      cards: cards.map((card) => {
        const blocks = [...card.querySelectorAll('.path-family-block')];
        return {
          blockCount: blocks.length,
          families: blocks.map((block) => block.querySelector('.path-family-label')?.textContent?.trim() || ''),
          values: blocks.map((block) => block.querySelector('.path-family-value')?.textContent?.trim() || ''),
          text: card.textContent || ''
        };
      }),
      expected: family === 'ipv6' ? 'IPv6' : 'IPv4',
      forbidden: opposite === 'ipv6' ? 'IPv6' : 'IPv4'
    };
  }, {family, opposite});
  assert(snapshot.cards.length > 0, `${family} Internet Exit picker has no options`);
  for (const card of snapshot.cards) {
    assert(card.blockCount === 1, `${family} Internet Exit option rendered ${card.blockCount} family blocks`);
    assert(card.families[0] === snapshot.expected, `${family} Internet Exit option rendered wrong family ${card.families[0]}`);
    assert(!card.families.includes(snapshot.forbidden), `${family} Internet Exit option leaked ${snapshot.forbidden}`);
    assert(!card.values.some((value) => /^\[[^\]]+\]:\d+$/.test(value) || /^\d{1,3}(?:\.\d{1,3}){3}:\d+$/.test(value)), `${family} Internet Exit option leaked Access endpoint port identity`);
  }
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('#endpoint-picker-layer')?.classList.contains('open'));
}

async function assertModeVisibility(page, mode) {
  const visibility = await page.evaluate(() => ({
    v4: !document.querySelector('#egress-ipv4-select')?.closest('.field')?.hidden,
    v6: !document.querySelector('#egress-ipv6-select')?.closest('.field')?.hidden,
  }));
  if (mode === 'ipv4') assert(visibility.v4 && !visibility.v6, 'IPv4 mode did not expose only IPv4 Internet Exit');
  if (mode === 'ipv6') assert(!visibility.v4 && visibility.v6, 'IPv6 mode did not expose only IPv6 Internet Exit');
  if (mode === 'dual') assert(visibility.v4 && visibility.v6, 'Dual mode did not expose one picker per family');
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
  await assertModeVisibility(page, 'ipv4');
  await assertExitPicker(page, 'ipv4');

  await page.selectOption('#egress-ipv4-select', 'WAN');
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN');
  await page.waitForTimeout(100);
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN', 'manual IPv4 Internet Exit was overwritten by its own render');

  await page.locator('[data-family="ipv6"]').click();
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'ipv6');
  await page.waitForFunction(() => document.querySelector('#egress-ipv6-select')?.value === 'WAN2');
  await assertModeVisibility(page, 'ipv6');
  await assertExitPicker(page, 'ipv6');

  await page.locator('[data-family="ipv4"]').click();
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'ipv4');
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN');
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN', 'manual IPv4 Internet Exit was not restored after Access-family switching');

  await selectExitMode(page, 'dual');
  await assertModeVisibility(page, 'dual');
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN', 'Dual did not retain the explicit IPv4 WAN scalar');
  assert(await page.locator('#egress-ipv6-select').inputValue() === 'WAN2', 'Dual did not use the independently recommended IPv6 WAN scalar');
  await assertExitPicker(page, 'ipv4');
  await assertExitPicker(page, 'ipv6');

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
  await page.close();

  const desktop = await browser.newPage({viewport: {width: 1366, height: 768}});
  await desktop.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await desktop.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'ipv4');
  await assertModeVisibility(desktop, 'ipv4');
  await assertExitPicker(desktop, 'ipv4');
  await selectExitMode(desktop, 'ipv6');
  await assertModeVisibility(desktop, 'ipv6');
  await assertExitPicker(desktop, 'ipv6');
  await desktop.close();

  console.log('Browser Internet Exit regression passed: mobile/desktop share one picker, single-family modes expose only their family, Dual uses two scalar pickers, no Access port identity leaks, and zero auto-Activate.');
} finally {
  await browser.close();
}
