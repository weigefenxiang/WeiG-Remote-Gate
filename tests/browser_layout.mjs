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

    const v032 = await page.evaluate(() => ({
      brandSrc: document.querySelector('.brand-icon-image')?.getAttribute('src'),
      brandChassis: document.querySelector('#utility-trigger')?.classList.contains('brand-icon-chassis'),
      nativeHidden: document.querySelector('#endpoint-select')?.classList.contains('endpoint-native-select'),
      presetLabels: [...document.querySelectorAll('#ttl-segment button')].map((node) => node.textContent.trim()),
      customMin: document.querySelector('#duration-slider')?.min,
      customMax: document.querySelector('#duration-slider')?.max,
      customStep: document.querySelector('#duration-slider')?.step,
      dualPresent: Boolean(document.querySelector('[data-family="dual"]')),
      feedbackReady: Boolean(window.RemoteGateFeedback?.notify),
    }));
    assert(v032.brandSrc === '/static/Wei.G.ico', `${width}x${height}: header is not using Wei.G.ico`);
    assert(v032.brandChassis, `${width}x${height}: brand icon 3D chassis missing`);
    assert(v032.nativeHidden, `${width}x${height}: native endpoint select is still visual`);
    assert(v032.dualPresent, `${width}x${height}: dual-stack family control missing`);
    assert(v032.feedbackReady, `${width}x${height}: standard feedback module not loaded`);
    assert(JSON.stringify(v032.presetLabels) === JSON.stringify(['1m', '5m', '15m', '30m', 'Custom']), `${width}x${height}: wrong TTL presets ${v032.presetLabels}`);
    assert(!v032.presetLabels.includes('1h'), `${width}x${height}: forbidden 1h preset present`);
    assert(v032.customMin === '1800' && v032.customMax === '43200' && v032.customStep === '1800', `${width}x${height}: custom duration bounds/step incorrect`);

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

    const autoFamily = await page.locator('#family-segment .active').getAttribute('data-family');
    assert(autoFamily === 'ipv4', `${width}x${height}: IPv4 was not preferred automatically`);

    await page.locator('#endpoint-picker-trigger').click();
    await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card');
    const picker = await page.evaluate(() => {
      const sheet = document.querySelector('#endpoint-picker-layer .endpoint-picker-sheet');
      const handle = document.querySelector('#endpoint-picker-layer .endpoint-picker-handle');
      const r = sheet.getBoundingClientRect();
      const style = getComputedStyle(sheet);
      return {
        optionCount: document.querySelectorAll('#endpoint-picker-layer .endpoint-option-card').length,
        selected: document.querySelectorAll('#endpoint-picker-layer .endpoint-option-card.selected').length,
        open: document.querySelector('#endpoint-picker-trigger')?.getAttribute('aria-expanded'),
        centerY: (r.top + r.bottom) / 2,
        viewportCenterY: window.innerHeight / 2,
        left: r.left,
        right: r.right,
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        handleDisplay: handle ? getComputedStyle(handle).display : '',
        bottomRadius: parseFloat(style.borderBottomLeftRadius),
      };
    });
    assert(picker.optionCount >= 1, `${width}x${height}: endpoint picker has no cards`);
    assert(picker.selected === 1, `${width}x${height}: endpoint picker selected state missing`);
    assert(picker.open === 'true', `${width}x${height}: endpoint picker did not expose open state`);
    if (width <= 767) {
      assert(Math.abs(picker.centerY - picker.viewportCenterY) <= 16, `${width}x${height}: mobile picker is not vertically centered`);
      assert(picker.left >= 11 && picker.right <= picker.innerWidth - 11, `${width}x${height}: mobile picker does not preserve side insets`);
      assert(picker.scrollWidth <= picker.innerWidth + 1, `${width}x${height}: picker creates horizontal overflow`);
      assert(picker.handleDisplay === 'none', `${width}x${height}: bottom-sheet handle is still visible`);
      assert(picker.bottomRadius >= 20, `${width}x${height}: mobile picker bottom corners are not rounded`);
    }
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
    assert(!('source_ip' in body) && !('address' in body), `${width}x${height}: authorization request included a browser address`);

    await page.waitForFunction(() => window.RemoteGateGateControls?.transactionLocked?.());
    const lockedFamily = await page.locator('#family-segment .active').getAttribute('data-family');
    await page.evaluate(() => document.querySelector('[data-family="ipv6"]')?.click());
    await page.waitForSelector('.feedback-card.feedback-info');
    const afterLockedClick = await page.locator('#family-segment .active').getAttribute('data-family');
    assert(afterLockedClick === lockedFamily, `${width}x${height}: transaction lock allowed family change`);
    assert(await page.locator('.gate-form').evaluate((node) => node.classList.contains('transaction-locked')), `${width}x${height}: transaction lock visual state missing`);

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

  // Dual-stack regression: one click submits two families without any browser-supplied source address.
  const dualPage = await browser.newPage({viewport: {width: 390, height: 844}});
  await dualPage.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await dualPage.waitForSelector('[data-family="dual"]');
  await dualPage.locator('[data-family="dual"]').click();
  assert(!(await dualPage.locator('#activate-button').isDisabled()), 'dual-stack selection did not enable Activate');
  const dualRequestPromise = dualPage.waitForRequest((request) => request.url().endsWith('/api/v1/gate/activate') && request.method() === 'POST');
  await dualPage.locator('#activate-button').click();
  const dualBody = (await dualRequestPromise).postDataJSON();
  assert(JSON.stringify(dualBody.families) === JSON.stringify(['ipv4', 'ipv6']), 'dual-stack family list is incorrect');
  assert(dualBody.endpoint_ids?.ipv4 === 'ep-wan2-v4', 'dual-stack IPv4 endpoint is incorrect');
  assert(dualBody.endpoint_ids?.ipv6 === 'ep-wan2-v6', 'dual-stack IPv6 endpoint is incorrect');
  assert(!('source_ip' in dualBody) && !('address' in dualBody), 'dual-stack authorization request included a browser address');
  await dualPage.close();

  // IPv6-first request with no IPv4 source: primary echo may fail, fallback may save an untrusted candidate.
  // Candidate success must update the current page in-place; it must never navigate/reload the document.
  const sourcePage = await browser.newPage({viewport: {width: 390, height: 844}});
  let candidateSaved = false;
  let primaryRequests = 0;
  let fallbackRequests = 0;
  let candidatePosts = 0;
  let candidateBody = null;
  let releaseFallback;
  let markFallbackStarted;
  const fallbackGate = new Promise((resolve) => { releaseFallback = resolve; });
  const fallbackStarted = new Promise((resolve) => { markFallbackStarted = resolve; });

  await sourcePage.route('**/api/v1/dashboard', async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.inventory.capabilities.gate_ipv6 = false;
    if (candidateSaved) {
      const now = Math.floor(Date.now() / 1000);
      payload.client_sources.ipv4 = {
        address: '112.96.156.107',
        observed_at: now,
        expires_at: now + 300,
        source: 'carrier_probe',
        confidence: 'candidate',
      };
    } else {
      delete payload.client_sources.ipv4;
    }
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });

  await sourcePage.route('https://api.ipify.org/**', async (route) => {
    primaryRequests += 1;
    await route.abort('failed');
  });
  await sourcePage.route('https://api-ipv4.ip.sb/**', async (route) => {
    fallbackRequests += 1;
    markFallbackStarted();
    await fallbackGate;
    await route.fulfill({
      status: 200,
      contentType: 'text/plain',
      headers: {'Access-Control-Allow-Origin': '*'},
      body: '112.96.156.107\n',
    });
  });

  await sourcePage.route('**/api/v1/client-source/candidate', async (route) => {
    candidatePosts += 1;
    candidateBody = route.request().postDataJSON();
    assert(route.request().headers()['x-csrf-token'] === 'fixture-csrf', 'candidate request lost CSRF binding');
    assert(candidateBody.family === 'ipv4', 'candidate request used wrong family');
    assert(candidateBody.address === '112.96.156.107', 'candidate request used wrong IPv4');
    assert(!('source_ip' in candidateBody), 'candidate endpoint used authorization source_ip field');
    candidateSaved = true;
    const now = Math.floor(Date.now() / 1000);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        family: 'ipv4',
        address: '112.96.156.107',
        observed_at: now,
        expires_at: now + 300,
        source: 'carrier_probe',
        confidence: 'candidate',
      }),
    });
  });

  await sourcePage.goto('http://127.0.0.1:8765/', {waitUntil: 'domcontentloaded'});
  await fallbackStarted;
  await sourcePage.waitForSelector('#endpoint-picker-trigger');
  await sourcePage.waitForFunction(() =>
    document.querySelector('#family-segment .active')?.dataset.family === 'ipv4' &&
    document.querySelector('#endpoint-select')?.value === 'ep-wan2-v4'
  );

  const marker = await sourcePage.evaluate(() => {
    window.__remoteGateNoReloadMarker = `marker-${Math.random()}`;
    return window.__remoteGateNoReloadMarker;
  });
  const beforeCandidate = await sourcePage.evaluate(() => ({
    family: document.querySelector('#family-segment .active')?.dataset.family,
    endpoint: document.querySelector('#endpoint-select')?.value,
    activateDisabled: document.querySelector('#activate-button')?.disabled,
    ipv6Disabled: document.querySelector('[data-family="ipv6"]')?.disabled,
    ipv4Source: document.querySelector('#client-ipv4')?.textContent,
  }));
  assert(beforeCandidate.family === 'ipv4', 'missing IPv4 source incorrectly fell back to request IPv6');
  assert(beforeCandidate.endpoint === 'ep-wan2-v4', 'IPv4 endpoint disappeared while its source was missing');
  assert(beforeCandidate.activateDisabled, 'Activate enabled before an IPv4 candidate existed');
  assert(beforeCandidate.ipv6Disabled, 'disabled IPv6 Gate remained selectable');
  assert(beforeCandidate.ipv4Source !== '112.96.156.107', 'fixture unexpectedly started with an IPv4 source');

  releaseFallback();
  await sourcePage.waitForFunction(() =>
    document.querySelector('#client-ipv4')?.textContent === '112.96.156.107' &&
    !document.querySelector('#activate-button')?.disabled
  );

  assert(primaryRequests === 1, `primary IPv4 echo should be requested exactly once (${primaryRequests})`);
  assert(fallbackRequests === 1, `fallback IPv4 echo should be requested exactly once (${fallbackRequests})`);
  assert(candidatePosts === 1, `IPv4 candidate should be submitted exactly once (${candidatePosts})`);
  assert(candidateBody?.address === '112.96.156.107', 'candidate body was not preserved');
  assert(await sourcePage.evaluate((expected) => window.__remoteGateNoReloadMarker === expected, marker), 'candidate success reloaded/navigated the page');

  const candidateActivatePromise = sourcePage.waitForRequest((request) => request.url().endsWith('/api/v1/gate/activate') && request.method() === 'POST');
  await sourcePage.locator('#activate-button').click();
  const candidateActivate = (await candidateActivatePromise).postDataJSON();
  assert(candidateActivate.family === 'ipv4', 'candidate recovery changed the selected family');
  assert(candidateActivate.endpoint_id === 'ep-wan2-v4', 'candidate recovery changed the selected endpoint');
  assert(!('source_ip' in candidateActivate) && !('address' in candidateActivate), 'candidate leaked into the authorization request');
  await sourcePage.unrouteAll({behavior: 'ignoreErrors'});
  await sourcePage.close();

  // When Cloudflare already observed IPv4, the browser must not call an IPv4 carrier probe at all.
  const observedPage = await browser.newPage({viewport: {width: 390, height: 844}});
  let observedIpv4Probe = 0;
  await observedPage.route('https://api.ipify.org/**', async (route) => { observedIpv4Probe += 1; await route.abort('failed'); });
  await observedPage.route('https://api-ipv4.ip.sb/**', async (route) => { observedIpv4Probe += 1; await route.abort('failed'); });
  await observedPage.route('**/api/v1/dashboard', async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    const now = Math.floor(Date.now() / 1000);
    payload.client_sources.ipv4 = {
      address: '112.96.150.36',
      observed_at: now,
      expires_at: now + 600,
      source: 'cloudflare',
      confidence: 'observed',
    };
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });
  await observedPage.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await observedPage.waitForFunction(() => document.querySelector('#client-ipv4')?.textContent === '112.96.150.36');
  await observedPage.waitForTimeout(250);
  assert(observedIpv4Probe === 0, `Cloudflare-observed IPv4 unexpectedly triggered carrier probe (${observedIpv4Probe})`);
  await observedPage.unrouteAll({behavior: 'ignoreErrors'});
  await observedPage.close();

  console.log(`Browser layout regression passed for ${viewports.length} viewports plus dual-stack, transaction lock, fallback candidate recovery, and observed-source probe suppression.`);
} finally {
  await browser.close();
}
