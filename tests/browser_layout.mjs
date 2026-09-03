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

async function chooseEndpoint(page, selectId, value) {
  const trigger = selectId === 'endpoint-select' ? '#endpoint-picker-trigger' : `#${selectId}-picker-trigger`;
  await page.locator(trigger).click();
  await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card');
  await page.locator(`#endpoint-picker-layer .endpoint-option-card[data-value="${value}"]`).click();
  await page.waitForFunction(({selectId, value}) => document.querySelector(`#${selectId}`)?.value === value, {selectId, value});
}

async function waitForAutoEndpoint(page, selectId, value) {
  await page.waitForFunction(({selectId, value}) => {
    const select = document.querySelector(`#${selectId}`);
    return select?.value === value
      && select.dataset.selectionConfirmed === '1'
      && select.dataset.selectionSource === 'auto';
  }, {selectId, value});
}

async function waitForExit(page, mode, wan4 = '', wan6 = '') {
  await page.waitForFunction((expected) => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === expected, mode);
  if (wan4) await page.waitForFunction((expected) => document.querySelector('#egress-ipv4-select')?.value === expected, wan4);
  if (wan6) await page.waitForFunction((expected) => document.querySelector('#egress-ipv6-select')?.value === expected, wan6);
}

async function assertAccessLayout(page, expectedLayout = 'adaptive') {
  const geometry = await page.evaluate(() => {
    const root = document.querySelector('.access-family-selectors');
    const fields = [...(root?.querySelectorAll(':scope > [data-access-slot]') || [])].filter((node) => !node.hidden);
    const boxes = fields.map((node) => {
      const r = node.getBoundingClientRect();
      return {slot:node.dataset.accessSlot, family:node.dataset.accessFamily, left:r.left, right:r.right, top:r.top, bottom:r.bottom, width:r.width};
    });
    const rr = root?.getBoundingClientRect();
    return {display:root ? getComputedStyle(root).display : '', boxes, rootWidth:rr?.width || 0, innerWidth:window.innerWidth, scrollWidth:document.documentElement.scrollWidth};
  });
  assert(geometry.display === 'grid', 'Access family selectors are not using the shared grid');
  assert(geometry.scrollWidth <= geometry.innerWidth + 1, `Access selectors overflow horizontally (${geometry.scrollWidth}/${geometry.innerWidth})`);
  assert(geometry.boxes.length === 2, `Dual Access must expose exactly two scalar fields (${geometry.boxes.length})`);
  assert(geometry.boxes[0].family === 'ipv4' && geometry.boxes[1].family === 'ipv6', `Dual Access DOM order changed (${geometry.boxes.map((x) => x.family).join(',')})`);
  const [v4, v6] = geometry.boxes;
  const sameRow = Math.abs(v4.top - v6.top) <= 1.5;
  if (expectedLayout === 'stacked') {
    assert(v4.top < v6.top - 1, `Dual Access mobile order is not IPv4 above IPv6 (${v4.top}/${v6.top})`);
    assert(Math.abs(v4.width - geometry.rootWidth) <= 1.5 && Math.abs(v6.width - geometry.rootWidth) <= 1.5, 'Dual Access stacked fields are not full width');
  } else if (sameRow) {
    assert(v4.right <= v6.left + 1.5, 'Adaptive Dual Access fields overlap or reverse family order');
  } else {
    assert(v4.top < v6.top - 1, 'Adaptive Dual Access stack reversed family order');
  }
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
    await waitForAutoEndpoint(page, 'endpoint-select', 'ep-wan2-v4');
    await waitForExit(page, 'ipv4', 'WAN2');
    await page.waitForFunction(() => document.querySelector('#activate-button') && !document.querySelector('#activate-button').disabled);

    const initial = await page.evaluate(() => ({
      brandSrc: document.querySelector('.brand-icon-image')?.getAttribute('src'),
      brandChassis: document.querySelector('#utility-trigger')?.classList.contains('brand-icon-chassis'),
      nativeHidden: document.querySelector('#endpoint-select')?.classList.contains('endpoint-native-select'),
      endpointValue: document.querySelector('#endpoint-select')?.value,
      endpointConfirmed: document.querySelector('#endpoint-select')?.dataset.selectionConfirmed,
      endpointSource: document.querySelector('#endpoint-select')?.dataset.selectionSource,
      accessFields: [...document.querySelectorAll('.access-family-selectors > [data-access-slot]')].filter((node) => !node.hidden).map((node) => node.dataset.accessFamily),
      egressMode: document.querySelector('#egress-mode-segment .active')?.dataset.egressMode,
      egress4: document.querySelector('#egress-ipv4-select')?.value,
      presetLabels: [...document.querySelectorAll('#ttl-segment button')].map((node) => node.textContent.trim()),
      customMin: document.querySelector('#duration-slider')?.min,
      customMax: document.querySelector('#duration-slider')?.max,
      customStep: document.querySelector('#duration-slider')?.step,
      dualPresent: Boolean(document.querySelector('[data-family="dual"]')),
      feedbackReady: Boolean(window.RemoteGateFeedback?.notify),
    }));
    assert(initial.brandSrc === '/static/Wei.G.ico', `${width}x${height}: header is not using Wei.G.ico`);
    assert(initial.brandChassis, `${width}x${height}: brand icon 3D chassis missing`);
    assert(initial.nativeHidden, `${width}x${height}: native endpoint select is still visual`);
    assert(initial.endpointValue === 'ep-wan2-v4', `${width}x${height}: best public IPv4 endpoint was not selected automatically`);
    assert(initial.endpointConfirmed === '1' && initial.endpointSource === 'auto', `${width}x${height}: automatic endpoint selection metadata is wrong`);
    assert(JSON.stringify(initial.accessFields) === JSON.stringify(['ipv4']), `${width}x${height}: IPv4 mode did not expose exactly one Access scalar (${initial.accessFields})`);
    assert(initial.egressMode === 'ipv4' && initial.egress4 === 'WAN2', `${width}x${height}: IPv4 Internet Exit did not default to WAN2`);
    assert(initial.dualPresent && initial.feedbackReady, `${width}x${height}: required Gate controls/modules missing`);
    assert(JSON.stringify(initial.presetLabels) === JSON.stringify(['1m', '5m', '15m', '30m', 'Custom']), `${width}x${height}: wrong TTL presets ${initial.presetLabels}`);
    assert(initial.customMin === '1800' && initial.customMax === '43200' && initial.customStep === '1800', `${width}x${height}: custom duration bounds/step incorrect`);

    const geometry = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('.workspace-card')].map((node) => {
        const r = node.getBoundingClientRect();
        return {id: node.dataset.cardId, left: r.left, right: r.right, top: r.top, bottom: r.bottom};
      });
      return {
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        cards,
        flowOrder: [...document.querySelectorAll('.workspace-flow > [data-card-id]')].map((node) => node.dataset.cardId),
        main: (() => { const r = document.querySelector('.workspace-main')?.getBoundingClientRect(); return r ? {top:r.top,bottom:r.bottom} : null; })(),
        rail: (() => { const r = document.querySelector('.workspace-rail')?.getBoundingClientRect(); return r ? {top:r.top,bottom:r.bottom} : null; })(),
      };
    });
    assert(geometry.scrollWidth <= geometry.innerWidth + 1, `${width}x${height}: horizontal overflow ${geometry.scrollWidth} > ${geometry.innerWidth}`);
    for (let i = 0; i < geometry.cards.length; i += 1) {
      for (let j = i + 1; j < geometry.cards.length; j += 1) {
        assert(overlap(geometry.cards[i], geometry.cards[j]) <= 1, `${width}x${height}: card overlap ${geometry.cards[i].id}/${geometry.cards[j].id}`);
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
          '#egress-mode-segment button:not([disabled])', '#egress-ipv4-select-picker-trigger:not([hidden])', '#egress-ipv6-select-picker-trigger:not([hidden])',
          '.activity-row', '.wan-address-copy'
        ];
        return selectors.flatMap((selector) => [...document.querySelectorAll(selector)]).filter((node) => !node.closest('[hidden]')).map((node) => {
          const r = node.getBoundingClientRect();
          return {selector: node.id || node.className || node.tagName, height: r.height};
        });
      });
      for (const target of touchTargets) assert(target.height >= 43.5, `${width}x${height}: touch target too short ${target.selector} ${target.height}`);
    }

    const ipv6 = await page.evaluate(() => {
      const node = document.querySelector('#client-ipv6');
      const card = node.closest('.workspace-card');
      const r = node.getBoundingClientRect();
      const cr = card.getBoundingClientRect();
      return {whiteSpace: getComputedStyle(node).whiteSpace, right: r.right, cardRight: cr.right, text: node.textContent};
    });
    assert(ipv6.whiteSpace === 'nowrap', `${width}x${height}: IPv6 can wrap`);
    assert(ipv6.right <= ipv6.cardRight + 1 && ipv6.text.includes(':'), `${width}x${height}: IPv6 identity layout is broken`);

    await page.locator('#endpoint-picker-trigger').click();
    await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card');
    const picker = await page.evaluate(() => {
      const sheet = document.querySelector('#endpoint-picker-layer .endpoint-picker-sheet');
      const handle = document.querySelector('#endpoint-picker-layer .endpoint-picker-handle');
      const selected = document.querySelector('#endpoint-picker-layer .endpoint-option-card.selected');
      const r = sheet.getBoundingClientRect();
      const style = getComputedStyle(sheet);
      return {
        optionCount: document.querySelectorAll('#endpoint-picker-layer .endpoint-option-card').length,
        selected: document.querySelectorAll('#endpoint-picker-layer .endpoint-option-card.selected').length,
        selectedBlocks: selected?.querySelectorAll('.path-family-block').length || 0,
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
    assert(picker.optionCount >= 1 && picker.selected === 1 && picker.selectedBlocks === 1, `${width}x${height}: scalar Access picker state is invalid`);
    if (width <= 767) {
      assert(Math.abs(picker.centerY - picker.viewportCenterY) <= 16, `${width}x${height}: mobile picker is not vertically centered`);
      assert(picker.left >= 11 && picker.right <= picker.innerWidth - 11, `${width}x${height}: mobile picker does not preserve side insets`);
      assert(picker.scrollWidth <= picker.innerWidth + 1 && picker.handleDisplay === 'none' && picker.bottomRadius >= 20, `${width}x${height}: mobile picker chrome regression`);
    }
    await page.keyboard.press('Escape');

    await page.locator('#ttl-custom-button').click();
    await page.locator('#duration-slider').fill('7200');
    const duration = await page.evaluate(() => ({
      hidden: document.querySelector('#duration-custom-panel')?.hidden,
      value: document.querySelector('#duration-slider')?.value,
      output: document.querySelector('#duration-output')?.textContent,
      active: document.querySelector('#ttl-custom-button')?.classList.contains('active'),
    }));
    assert(!duration.hidden && duration.value === '7200' && duration.output === '2h' && duration.active, `${width}x${height}: custom duration regression`);

    await page.locator('[data-scope="wg_ping"]').click();
    const requestPromise = page.waitForRequest((request) => request.url().endsWith('/api/v1/gate/activate') && request.method() === 'POST');
    await page.locator('#activate-button').click();
    const body = (await requestPromise).postDataJSON();
    assert(body.endpoint_id === 'ep-wan2-v4' && body.family === 'ipv4', `${width}x${height}: IPv4 Access payload changed`);
    assert(body.egress_mode === 'ipv4' && body.egress_wan === 'WAN2' && body.egress_wans?.ipv4 === 'WAN2' && body.egress_wans?.ipv6 === '', `${width}x${height}: IPv4 Exit payload changed`);
    assert(body.scope === 'wg_ping' && body.ttl === 7200, `${width}x${height}: scope/TTL payload changed`);
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
    await page.locator('[data-family="ipv6"]').click();
    await waitForAutoEndpoint(page, 'endpoint-select', 'ep-wan2-v6');
    await waitForExit(page, 'ipv6', '', 'WAN2');
    assert(!(await page.locator('#activate-button').isDisabled()), `${width}x${height}: automatic IPv6 endpoint did not enable Activate`);

    await chooseEndpoint(page, 'endpoint-select', 'ep-wan-v6');
    await page.waitForFunction(() => document.querySelector('#endpoint-select')?.dataset.selectionSource === 'manual');
    assert((await page.locator('#egress-ipv6-select').inputValue()) === 'WAN2', `${width}x${height}: Access WAN change rewrote independent IPv6 Internet Exit`);

    assert(consoleErrors.length === 0, `${width}x${height}: browser console errors: ${consoleErrors.join(' | ')}`);
    await page.close();
  }

  for (const [width, height, layout] of [[390, 844, 'stacked'], [1366, 768, 'adaptive']]) {
    const dualPage = await browser.newPage({viewport: {width, height}});
    await dualPage.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
    await dualPage.locator('[data-family="dual"]').click();
    await waitForAutoEndpoint(dualPage, 'endpoint-select', 'ep-wan2-v4');
    await waitForAutoEndpoint(dualPage, 'access-ipv6-select', 'ep-wan2-v6');
    await waitForExit(dualPage, 'dual', 'WAN2', 'WAN2');
    await assertAccessLayout(dualPage, layout);
    const redundantLabels = await dualPage.evaluate(() => ({
      access: [...document.querySelectorAll('.access-family-selectors > .field > span')].filter((node) => !node.hidden && getComputedStyle(node).display !== 'none').map((node) => node.textContent.trim()),
      exit: [...document.querySelectorAll('.egress-family-selectors > .field > span')].filter((node) => !node.hidden && getComputedStyle(node).display !== 'none').map((node) => node.textContent.trim()),
    }));
    assert(redundantLabels.access.length === 0, `${width}: Dual Access rendered redundant per-family headings (${redundantLabels.access.join(',')})`);
    assert(redundantLabels.exit.length === 0, `${width}: Dual Internet Exit rendered redundant per-family headings (${redundantLabels.exit.join(',')})`);
    assert(!(await dualPage.locator('#activate-button').isDisabled()), `${width}: automatic Dual scalar selection did not enable Activate`);

    for (const [trigger, family] of [['#endpoint-picker-trigger', 'IPv4'], ['#access-ipv6-select-picker-trigger', 'IPv6']]) {
      await dualPage.locator(trigger).click();
      await dualPage.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card.selected');
      const scalar = await dualPage.locator('#endpoint-picker-layer .endpoint-option-card.selected').evaluate((root) => ({
        blocks:root.querySelectorAll('.path-family-block').length,
        family:root.querySelector('.path-family-label')?.textContent?.trim() || '',
      }));
      assert(scalar.blocks === 1 && scalar.family === family, `${width}: Dual ${family} selector is not family-pure`);
      await dualPage.keyboard.press('Escape');
    }

    const pairIds = await dualPage.evaluate(() => [...document.querySelectorAll('#endpoint-select option, #access-ipv6-select option')].map((option) => option.value).filter((value) => String(value).startsWith('dual:')));
    assert(pairIds.length === 0, `${width}: Dual generated pair IDs (${pairIds.join(',')})`);

    const dualRequestPromise = dualPage.waitForRequest((request) => request.url().endsWith('/api/v1/gate/activate') && request.method() === 'POST');
    await dualPage.locator('#activate-button').click();
    const dualBody = (await dualRequestPromise).postDataJSON();
    assert(JSON.stringify(dualBody.families) === JSON.stringify(['ipv4', 'ipv6']), `${width}: dual-stack family list is incorrect`);
    assert(dualBody.endpoint_ids?.ipv4 === 'ep-wan2-v4' && dualBody.endpoint_ids?.ipv6 === 'ep-wan2-v6', `${width}: Dual scalar endpoint_ids are incorrect`);
    assert(dualBody.egress_mode === 'dual' && dualBody.egress_wan === 'WAN2', `${width}: same-WAN Dual Exit payload is incorrect`);
    assert(!('source_ip' in dualBody) && !('address' in dualBody), `${width}: dual-stack authorization request included a browser source address`);
    await dualPage.close();
  }

  // Candidate success updates the current page in-place while the automatic endpoint remains stable.
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
        address: '112.96.156.107', observed_at: now, expires_at: now + 300,
        source: 'carrier_probe', confidence: 'candidate',
      };
    } else {
      delete payload.client_sources.ipv4;
    }
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });
  await sourcePage.route('https://api.ipify.org/**', async (route) => { primaryRequests += 1; await route.abort('failed'); });
  await sourcePage.route('https://api-ipv4.ip.sb/**', async (route) => {
    fallbackRequests += 1;
    markFallbackStarted();
    await fallbackGate;
    await route.fulfill({status: 200, contentType: 'text/plain', headers: {'Access-Control-Allow-Origin': '*'}, body: '112.96.156.107\n'});
  });
  await sourcePage.route('**/api/v1/client-source/candidate', async (route) => {
    candidatePosts += 1;
    candidateBody = route.request().postDataJSON();
    assert(route.request().headers()['x-csrf-token'] === 'fixture-csrf', 'candidate request lost CSRF binding');
    assert(candidateBody.family === 'ipv4' && candidateBody.address === '112.96.156.107', 'candidate request used wrong address');
    assert(!('source_ip' in candidateBody), 'candidate endpoint used authorization source_ip field');
    candidateSaved = true;
    const now = Math.floor(Date.now() / 1000);
    await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({
      family: 'ipv4', address: '112.96.156.107', observed_at: now, expires_at: now + 300,
      source: 'carrier_probe', confidence: 'candidate',
    })});
  });

  await sourcePage.goto('http://127.0.0.1:8765/', {waitUntil: 'domcontentloaded'});
  await fallbackStarted;
  await sourcePage.waitForSelector('#endpoint-picker-trigger');
  await waitForAutoEndpoint(sourcePage, 'endpoint-select', 'ep-wan2-v4');
  const marker = await sourcePage.evaluate(() => {
    window.__remoteGateNoReloadMarker = `marker-${Math.random()}`;
    return window.__remoteGateNoReloadMarker;
  });
  const beforeCandidate = await sourcePage.evaluate(() => ({
    family: document.querySelector('#family-segment .active')?.dataset.family,
    endpoint: document.querySelector('#endpoint-select')?.value,
    source: document.querySelector('#endpoint-select')?.dataset.selectionSource,
    activateDisabled: document.querySelector('#activate-button')?.disabled,
    ipv4Source: document.querySelector('#client-ipv4')?.textContent,
  }));
  assert(beforeCandidate.family === 'ipv4', 'missing IPv4 source incorrectly changed family');
  assert(beforeCandidate.endpoint === 'ep-wan2-v4' && beforeCandidate.source === 'auto', 'automatic IPv4 endpoint disappeared while source was missing');
  assert(beforeCandidate.activateDisabled, 'Activate enabled before an IPv4 candidate existed');

  releaseFallback();
  await sourcePage.waitForFunction(() =>
    document.querySelector('#client-ipv4')?.textContent === '112.96.156.107' &&
    !document.querySelector('#activate-button')?.disabled
  );
  assert(primaryRequests === 1 && fallbackRequests === 1 && candidatePosts === 1, `candidate probe request counts changed (${primaryRequests}/${fallbackRequests}/${candidatePosts})`);
  assert(candidateBody?.address === '112.96.156.107', 'candidate body was not preserved');
  assert(await sourcePage.evaluate((expected) => window.__remoteGateNoReloadMarker === expected, marker), 'candidate success reloaded/navigated the page');
  const candidateEndpoint = await sourcePage.evaluate(() => ({
    value: document.querySelector('#endpoint-select')?.value,
    source: document.querySelector('#endpoint-select')?.dataset.selectionSource,
  }));
  assert(candidateEndpoint.value === 'ep-wan2-v4' && candidateEndpoint.source === 'auto', 'candidate recovery changed automatic endpoint intent');
  await sourcePage.unrouteAll({behavior: 'ignoreErrors'});
  await sourcePage.close();

  // Cloudflare-observed IPv4 must suppress carrier probing.
  const observedPage = await browser.newPage({viewport: {width: 390, height: 844}});
  let observedIpv4Probe = 0;
  await observedPage.route('https://api.ipify.org/**', async (route) => { observedIpv4Probe += 1; await route.abort('failed'); });
  await observedPage.route('https://api-ipv4.ip.sb/**', async (route) => { observedIpv4Probe += 1; await route.abort('failed'); });
  await observedPage.route('**/api/v1/dashboard', async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    const now = Math.floor(Date.now() / 1000);
    payload.client_sources.ipv4 = {
      address: '112.96.150.36', observed_at: now, expires_at: now + 600,
      source: 'cloudflare', confidence: 'observed',
    };
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });
  await observedPage.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await observedPage.waitForFunction(() => document.querySelector('#client-ipv4')?.textContent === '112.96.150.36');
  await waitForAutoEndpoint(observedPage, 'endpoint-select', 'ep-wan2-v4');
  await observedPage.waitForTimeout(250);
  assert(observedIpv4Probe === 0, `Cloudflare-observed IPv4 unexpectedly triggered carrier probe (${observedIpv4Probe})`);
  await observedPage.unrouteAll({behavior: 'ignoreErrors'});
  await observedPage.close();

  console.log(`Browser layout regression passed for ${viewports.length} viewports plus scalar Dual Access, mode-first Internet Exit, transaction lock, candidate recovery, and observed-source probe suppression.`);
} finally {
  await browser.close();
}
