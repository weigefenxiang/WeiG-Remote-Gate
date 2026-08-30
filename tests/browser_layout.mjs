import { chromium } from 'playwright';

const viewports = [
  [320, 800],
  [360, 800],
  [390, 844],
  [412, 915],
  [768, 1024],
  [1024, 768],
  [1366, 768],
  [1440, 900],
  [1920, 1080],
];

const MOBILE_ORDER = ['gate', 'client', 'wireguard', 'wan', 'activity', 'system'];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function overlap(a, b) {
  const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  return width * height;
}

const browser = await chromium.launch({headless: true});
try {
  for (const [width, height] of viewports) {
    const page = await browser.newPage({viewport: {width, height}});
    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (error) => consoleErrors.push(String(error)));

    await page.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
    await page.waitForSelector('#wan-list .wan-row');
    await page.waitForSelector('#endpoint-picker-trigger');
    await page.waitForSelector('.brand-icon-image');
    await page.waitForSelector('#ttl-custom-button');
    await page.waitForFunction(() => document.querySelector('#activate-button') && !document.querySelector('#activate-button').disabled);

    const v031 = await page.evaluate(() => ({
      brandSrc: document.querySelector('.brand-icon-image')?.getAttribute('src'),
      brandChassis: document.querySelector('#utility-trigger')?.classList.contains('brand-icon-chassis'),
      nativeHidden: document.querySelector('#endpoint-select')?.classList.contains('endpoint-native-select'),
      presetLabels: [...document.querySelectorAll('#ttl-segment button')].map((node) => node.textContent.trim()),
      customMin: document.querySelector('#duration-slider')?.min,
      customMax: document.querySelector('#duration-slider')?.max,
      customStep: document.querySelector('#duration-slider')?.step,
    }));
    assert(v031.brandSrc === '/static/Wei.G.ico', `${width}x${height}: header is not using Wei.G.ico`);
    assert(v031.brandChassis, `${width}x${height}: brand icon 3D chassis missing`);
    assert(v031.nativeHidden, `${width}x${height}: native endpoint select is still visual`);
    assert(JSON.stringify(v031.presetLabels) === JSON.stringify(['1m', '5m', '15m', '30m', 'Custom']), `${width}x${height}: wrong TTL presets ${v031.presetLabels}`);
    assert(!v031.presetLabels.includes('1h'), `${width}x${height}: forbidden 1h preset present`);
    assert(v031.customMin === '1800' && v031.customMax === '43200' && v031.customStep === '1800', `${width}x${height}: custom duration bounds/step incorrect`);

    const geometry = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('.workspace-card')].map((node) => {
        const r = node.getBoundingClientRect();
        return {id: node.dataset.cardId, left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height};
      });
      return {
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        cards,
        flowOrder: [...document.querySelectorAll('.workspace-flow > [data-card-id]')].map((node) => node.dataset.cardId),
        main: (() => { const r = document.querySelector('.workspace-main')?.getBoundingClientRect(); return r ? {top:r.top,bottom:r.bottom,height:r.height} : null; })(),
        rail: (() => { const r = document.querySelector('.workspace-rail')?.getBoundingClientRect(); return r ? {top:r.top,bottom:r.bottom,height:r.height} : null; })(),
      };
    });

    assert(geometry.scrollWidth <= geometry.innerWidth + 1, `${width}x${height}: horizontal overflow ${geometry.scrollWidth} > ${geometry.innerWidth}`);

    for (let i = 0; i < geometry.cards.length; i += 1) {
      for (let j = i + 1; j < geometry.cards.length; j += 1) {
        const a = geometry.cards[i];
        const b = geometry.cards[j];
        assert(overlap(a, b) <= 1, `${width}x${height}: card overlap ${a.id}/${b.id}`);
      }
    }

    if (width < 1200) {
      assert(JSON.stringify(geometry.flowOrder) === JSON.stringify(MOBILE_ORDER), `${width}x${height}: incorrect responsive card order ${geometry.flowOrder.join(',')}`);
    } else {
      assert(geometry.main && geometry.rail, `${width}x${height}: desktop zones missing`);
      assert(Math.abs(geometry.main.bottom - geometry.rail.bottom) <= 2, `${width}x${height}: desktop main/rail bottoms are not aligned`);
    }

    if (width <= 767) {
      const touchTargets = await page.evaluate(() => {
        const selectors = [
          '#utility-trigger', '#mobile-theme-toggle', '#gate-orb',
          '#family-segment button:not([disabled])', '#scope-segment button:not([disabled])',
          '#ttl-segment button:not([disabled])', '#endpoint-picker-trigger', '#wg-select', '#activate-button',
          '.activity-row', '.wan-address-copy'
        ];
        return selectors.flatMap((selector) => [...document.querySelectorAll(selector)]).map((node) => {
          const r = node.getBoundingClientRect();
          return {selector: node.id || node.className || node.tagName, width: r.width, height: r.height};
        });
      });
      for (const target of touchTargets) {
        assert(target.height >= 43.5, `${width}x${height}: touch target too short ${target.selector} ${target.height}`);
      }
    }

    const ipv6 = await page.evaluate(() => {
      const node = document.querySelector('#client-ipv6');
      const card = node.closest('.workspace-card');
      const style = getComputedStyle(node);
      const r = node.getBoundingClientRect();
      const cr = card.getBoundingClientRect();
      return {whiteSpace: style.whiteSpace, right: r.right, cardRight: cr.right, text: node.textContent};
    });
    assert(ipv6.whiteSpace === 'nowrap', `${width}x${height}: IPv6 can wrap`);
    assert(ipv6.right <= ipv6.cardRight + 1, `${width}x${height}: IPv6 escapes its card`);
    assert(ipv6.text.includes(':'), `${width}x${height}: fixture IPv6 missing`);

    // IPv4 is the automatic preferred family even though the fixture request itself is IPv6.
    const autoFamily = await page.locator('#family-segment .active').getAttribute('data-family');
    assert(autoFamily === 'ipv4', `${width}x${height}: IPv4 was not preferred automatically`);

    await page.locator('#endpoint-picker-trigger').click();
    await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card');
    const picker = await page.evaluate(() => ({
      optionCount: document.querySelectorAll('#endpoint-picker-layer .endpoint-option-card').length,
      selected: document.querySelectorAll('#endpoint-picker-layer .endpoint-option-card.selected').length,
      open: document.querySelector('#endpoint-picker-trigger')?.getAttribute('aria-expanded'),
    }));
    assert(picker.optionCount >= 1, `${width}x${height}: endpoint picker has no cards`);
    assert(picker.selected === 1, `${width}x${height}: endpoint picker selected state missing`);
    assert(picker.open === 'true', `${width}x${height}: endpoint picker did not expose open state`);
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.querySelector('#endpoint-picker-trigger')?.getAttribute('aria-expanded') === 'false');

    await page.locator('#ttl-custom-button').click();
    await page.locator('#duration-slider').fill('7200');
    const duration = await page.evaluate(() => ({
      hidden: document.querySelector('#duration-custom-panel')?.hidden,
      value: document.querySelector('#duration-slider')?.value,
      output: document.querySelector('#duration-output')?.textContent,
      active: document.querySelector('#ttl-custom-button')?.classList.contains('active'),
    }));
    assert(!duration.hidden, `${width}x${height}: custom duration panel did not open`);
    assert(duration.value === '7200', `${width}x${height}: custom duration value is not 2h`);
    assert(duration.output === '2h', `${width}x${height}: custom duration output incorrect (${duration.output})`);
    assert(duration.active, `${width}x${height}: custom duration did not become active`);

    await page.locator('[data-family="ipv4"]').click();
    await page.waitForFunction(() => document.querySelector('#endpoint-select')?.value === 'ep-wan2-v4');
    assert(!(await page.locator('#activate-button').isDisabled()), `${width}x${height}: manual IPv4 selection did not enable Activate`);

    await page.locator('[data-scope="wg_ping"]').click();
    const requestPromise = page.waitForRequest((request) => request.url().endsWith('/api/v1/gate/activate') && request.method() === 'POST');
    await page.locator('#activate-button').click();
    const request = await requestPromise;
    const body = request.postDataJSON();
    assert(body.endpoint_id === 'ep-wan2-v4', `${width}x${height}: endpoint_id not submitted`);
    assert(body.family === 'ipv4', `${width}x${height}: family not submitted`);
    assert(body.scope === 'wg_ping', `${width}x${height}: scope not submitted`);
    assert(body.ttl === 7200, `${width}x${height}: custom TTL not submitted (${body.ttl})`);
    assert(!('source_ip' in body), `${width}x${height}: browser must never submit source_ip`);

    await page.reload({waitUntil: 'networkidle'});
    await page.waitForSelector('#wan-list .wan-row');
    await page.waitForFunction(() => document.querySelector('[data-family="ipv6"]') && !document.querySelector('[data-family="ipv6"]').disabled);
    await page.locator('[data-family="ipv6"]').click();
    assert(!(await page.locator('#activate-button').isDisabled()), `${width}x${height}: manual IPv6 selection did not enable Activate`);
    await page.waitForTimeout(150);
    const manualFamily = await page.locator('#family-segment .active').getAttribute('data-family');
    assert(manualFamily === 'ipv6', `${width}x${height}: refresh logic stole manual IPv6 selection`);

    if (width >= 1200) {
      const typography = await page.evaluate(() => ({
        system: parseFloat(getComputedStyle(document.querySelector('.system-row span')).fontSize),
        activityTime: parseFloat(getComputedStyle(document.querySelector('.activity-row time')).fontSize),
      }));
      assert(typography.system >= 13, `${width}x${height}: System labels too small (${typography.system}px)`);
      assert(typography.activityTime >= 12, `${width}x${height}: Activity time too small (${typography.activityTime}px)`);
    }

    assert(consoleErrors.length === 0, `${width}x${height}: browser console errors: ${consoleErrors.join(' | ')}`);
    await page.close();
  }
  console.log(`Browser layout regression passed for ${viewports.length} viewports.`);
} finally {
  await browser.close();
}
