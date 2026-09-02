import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const cases = [
  {
    name: 'IPv4 Access with IPv6-only Exit',
    accessFamily: 'ipv4',
    endpoint: 'ep-wan2-v4',
    exitMode: 'ipv6',
    legacyWan: 'WAN',
    wan4: '',
    wan6: 'WAN',
  },
  {
    name: 'IPv4 Access with split Dual Exit',
    accessFamily: 'ipv4',
    endpoint: 'ep-wan2-v4',
    exitMode: 'dual',
    legacyWan: '',
    wan4: 'WAN',
    wan6: 'WAN2',
  },
  {
    name: 'IPv6 Access with IPv4-only Exit',
    accessFamily: 'ipv6',
    endpoint: 'ep-wan2-v6',
    exitMode: 'ipv4',
    legacyWan: 'WAN',
    wan4: 'WAN',
    wan6: '',
  },
  {
    name: 'IPv6 Access with split Dual Exit',
    accessFamily: 'ipv6',
    endpoint: 'ep-wan2-v6',
    exitMode: 'dual',
    legacyWan: '',
    wan4: 'WAN2',
    wan6: 'WAN',
  },
];

async function selectExit(page, testCase) {
  await page.locator(`#egress-mode-segment [data-egress-mode="${testCase.exitMode}"]`).click();
  await page.waitForFunction((mode) => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === mode, testCase.exitMode);
  if (testCase.exitMode === 'ipv4' || testCase.exitMode === 'dual') {
    await page.selectOption('#egress-ipv4-select', testCase.wan4);
    await page.waitForFunction((wan) => document.querySelector('#egress-ipv4-select')?.value === wan, testCase.wan4);
  }
  if (testCase.exitMode === 'ipv6' || testCase.exitMode === 'dual') {
    await page.selectOption('#egress-ipv6-select', testCase.wan6);
    await page.waitForFunction((wan) => document.querySelector('#egress-ipv6-select')?.value === wan, testCase.wan6);
  }
}

const browser = await chromium.launch({headless: true});
try {
  for (const testCase of cases) {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (error) => consoleErrors.push(String(error)));

    await page.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
    await page.waitForSelector(`[data-family="${testCase.accessFamily}"]`);
    const activeFamily = await page.locator('#family-segment .active').getAttribute('data-family');
    if (activeFamily !== testCase.accessFamily) await page.locator(`[data-family="${testCase.accessFamily}"]`).click();
    await page.waitForFunction((family) => document.querySelector('#family-segment .active')?.dataset.family === family, testCase.accessFamily);
    await page.waitForFunction((endpoint) => document.querySelector('#endpoint-select')?.value === endpoint, testCase.endpoint);

    await selectExit(page, testCase);

    const requestPromise = page.waitForRequest((request) =>
      request.url().endsWith('/api/v1/gate/activate') && request.method() === 'POST'
    );
    await page.locator('#activate-button').click();
    const body = (await requestPromise).postDataJSON();

    assert(body.family === testCase.accessFamily, `${testCase.name}: Access family changed (${body.family})`);
    assert(body.endpoint_id === testCase.endpoint, `${testCase.name}: Access Endpoint changed (${body.endpoint_id})`);
    assert(body.egress_mode === testCase.exitMode, `${testCase.name}: wrong egress_mode (${body.egress_mode})`);
    assert(body.egress_wan === testCase.legacyWan, `${testCase.name}: wrong legacy egress_wan (${body.egress_wan})`);
    assert(body.egress_wans?.ipv4 === testCase.wan4, `${testCase.name}: wrong IPv4 Exit WAN (${body.egress_wans?.ipv4})`);
    assert(body.egress_wans?.ipv6 === testCase.wan6, `${testCase.name}: wrong IPv6 Exit WAN (${body.egress_wans?.ipv6})`);
    assert(!('source_ip' in body) && !('address' in body), `${testCase.name}: browser source leaked into Activate request`);
    assert(consoleErrors.length === 0, `${testCase.name}: browser console errors: ${consoleErrors.join(' | ')}`);

    await page.close();
  }

  console.log('Mixed Access/Internet Exit browser regression passed with mode-first independent IPv4/IPv6 WAN selectors and split-Dual payloads.');
} finally {
  await browser.close();
}
