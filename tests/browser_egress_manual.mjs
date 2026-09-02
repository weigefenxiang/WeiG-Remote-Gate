import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function selectExitMode(page, mode) {
  await page.locator(`#egress-mode-segment [data-egress-mode="${mode}"]`).click();
  await page.waitForFunction((value) => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === value, mode);
}

async function assertExitPicker(page, family, expectedSurface) {
  const opposite = family === 'ipv4' ? 'ipv6' : 'ipv4';
  const trigger = page.locator(`#egress-${family}-select-picker-trigger`);
  assert(await trigger.isVisible(), `${family} Internet Exit trigger is not visible`);
  await trigger.click();
  await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card');
  await page.waitForFunction((surface) => document.querySelector('#endpoint-picker-layer')?.dataset.mode === surface, expectedSurface);
  const snapshot = await page.evaluate(({family, opposite}) => {
    const cards = [...document.querySelectorAll('#endpoint-picker-layer .endpoint-option-card')];
    return {
      surface: document.querySelector('#endpoint-picker-layer')?.dataset.mode || '',
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
  assert(snapshot.surface === expectedSurface, `${family} Internet Exit used ${snapshot.surface} instead of ${expectedSurface}`);
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
  if (mode === 'none') assert(!visibility.v4 && !visibility.v6, 'LAN mode left an Internet Exit family picker visible');
  if (mode === 'ipv4') assert(visibility.v4 && !visibility.v6, 'IPv4 mode did not expose only IPv4 Internet Exit');
  if (mode === 'ipv6') assert(!visibility.v4 && visibility.v6, 'IPv6 mode did not expose only IPv6 Internet Exit');
  if (mode === 'dual') assert(visibility.v4 && visibility.v6, 'Dual mode did not expose one picker per family');
}

async function assertExitLayout(page, mode, expectedLayout) {
  const geometry = await page.evaluate(() => {
    const root = document.querySelector('.egress-family-selectors');
    const fields = [...(root?.querySelectorAll(':scope > [data-egress-family]') || [])].filter((node) => !node.hidden);
    const boxes = Object.fromEntries(fields.map((node) => {
      const rect = node.getBoundingClientRect();
      return [node.dataset.egressFamily, {left:rect.left, right:rect.right, top:rect.top, bottom:rect.bottom, width:rect.width}];
    }));
    const rootRect = root?.getBoundingClientRect();
    return {
      display: root ? getComputedStyle(root).display : '',
      visibleFamilies: fields.map((node) => node.dataset.egressFamily),
      rootWidth: rootRect?.width || 0,
      boxes,
      innerWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
    };
  });

  assert(geometry.display === 'grid', `${mode}: Internet Exit family container is not the canonical grid`);
  assert(geometry.scrollWidth <= geometry.innerWidth + 1, `${mode}: Internet Exit caused horizontal overflow ${geometry.scrollWidth} > ${geometry.innerWidth}`);
  if (mode === 'none') {
    assert(geometry.visibleFamilies.length === 0, 'LAN mode rendered a WAN field');
    return;
  }
  if (mode === 'ipv4' || mode === 'ipv6') {
    assert(geometry.visibleFamilies.length === 1 && geometry.visibleFamilies[0] === mode, `${mode}: wrong visible family fields ${geometry.visibleFamilies.join(',')}`);
    const box = geometry.boxes[mode];
    assert(Math.abs(box.width - geometry.rootWidth) <= 1.5, `${mode}: single-family field did not span the selector width`);
    return;
  }

  assert(JSON.stringify(geometry.visibleFamilies) === JSON.stringify(['ipv4','ipv6']), `Dual field DOM order changed: ${geometry.visibleFamilies.join(',')}`);
  const v4 = geometry.boxes.ipv4;
  const v6 = geometry.boxes.ipv6;
  if (expectedLayout === 'stacked') {
    assert(v4.top < v6.top - 1, `Dual mobile fields are not stacked IPv4 above IPv6 (${v4.top}/${v6.top})`);
    assert(Math.abs(v4.left - v6.left) <= 1.5, 'Dual mobile fields do not share the same column');
    assert(Math.abs(v4.width - geometry.rootWidth) <= 1.5 && Math.abs(v6.width - geometry.rootWidth) <= 1.5, 'Dual mobile fields do not span the selector width');
  } else {
    assert(Math.abs(v4.top - v6.top) <= 1.5, `Dual desktop fields are not side by side (${v4.top}/${v6.top})`);
    assert(v4.right <= v6.left + 1.5, 'Dual desktop IPv4/IPv6 fields overlap or reversed');
  }
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
  await assertExitLayout(page, 'ipv4', 'stacked');
  await assertExitPicker(page, 'ipv4', 'sheet');

  await page.selectOption('#egress-ipv4-select', 'WAN');
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN');
  await page.waitForTimeout(100);
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN', 'manual IPv4 Internet Exit was overwritten by its own render');

  await page.locator('[data-family="ipv6"]').click();
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'ipv6');
  await page.waitForFunction(() => document.querySelector('#egress-ipv6-select')?.value === 'WAN2');
  await assertModeVisibility(page, 'ipv6');
  await assertExitLayout(page, 'ipv6', 'stacked');
  await assertExitPicker(page, 'ipv6', 'sheet');

  await page.locator('[data-family="ipv4"]').click();
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'ipv4');
  await page.waitForFunction(() => document.querySelector('#egress-ipv4-select')?.value === 'WAN');
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN', 'manual IPv4 Internet Exit was not restored after Access-family switching');

  await selectExitMode(page, 'dual');
  await assertModeVisibility(page, 'dual');
  await assertExitLayout(page, 'dual', 'stacked');
  assert(await page.locator('#egress-ipv4-select').inputValue() === 'WAN', 'Dual did not retain the explicit IPv4 WAN scalar');
  assert(await page.locator('#egress-ipv6-select').inputValue() === 'WAN2', 'Dual did not use the independently recommended IPv6 WAN scalar');
  await assertExitPicker(page, 'ipv4', 'sheet');
  await assertExitPicker(page, 'ipv6', 'sheet');

  await selectExitMode(page, 'none');
  await assertModeVisibility(page, 'none');
  await assertExitLayout(page, 'none', 'stacked');
  assert(!(await page.locator('#egress-ipv4-select-picker-trigger').isVisible()), 'LAN mode left IPv4 trigger visible');
  assert(!(await page.locator('#egress-ipv6-select-picker-trigger').isVisible()), 'LAN mode left IPv6 trigger visible');

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
  let desktopActivatePosts = 0;
  desktop.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/gate/activate') desktopActivatePosts += 1;
  });
  await desktop.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await desktop.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'ipv4');
  await assertModeVisibility(desktop, 'ipv4');
  await assertExitLayout(desktop, 'ipv4', 'side-by-side');
  await assertExitPicker(desktop, 'ipv4', 'popover');
  await selectExitMode(desktop, 'ipv6');
  await assertModeVisibility(desktop, 'ipv6');
  await assertExitLayout(desktop, 'ipv6', 'side-by-side');
  await assertExitPicker(desktop, 'ipv6', 'popover');
  await selectExitMode(desktop, 'dual');
  await assertModeVisibility(desktop, 'dual');
  await assertExitLayout(desktop, 'dual', 'side-by-side');
  await assertExitPicker(desktop, 'ipv4', 'popover');
  await assertExitPicker(desktop, 'ipv6', 'popover');
  await selectExitMode(desktop, 'none');
  await assertModeVisibility(desktop, 'none');
  await assertExitLayout(desktop, 'none', 'side-by-side');
  assert(desktopActivatePosts === 0, `desktop Internet Exit state changes posted Activate (${desktopActivatePosts})`);
  await desktop.close();

  console.log('Browser Internet Exit regression passed: LAN has zero WAN pickers, single-family modes span one family only, Dual uses one scalar per family with responsive layout, mobile uses the shared sheet, desktop uses the shared popover, no Access port identity leaks, and zero auto-Activate.');
} finally {
  await browser.close();
}
