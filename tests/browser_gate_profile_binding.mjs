import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function addAltWireGuard(payload) {
  const baseWg = payload.agent?.wireguard?.find((item) => item?.name === 'WG_HOME');
  if (!baseWg) throw new Error('fixture is missing WG_HOME');
  payload.agent.wireguard = [baseWg, {...baseWg, name: 'WG_ALT', listen_port: 41194}];
  const altEndpoints = payload.endpoints
    .filter((item) => item?.wireguard === 'WG_HOME')
    .map((item) => ({
      ...item,
      id: `${item.id}-alt`,
      wireguard: 'WG_ALT',
      service_id: 'wg.WG_ALT',
      external_port: item.reachability === 'mapped' ? item.external_port : 41194,
      ingress_port: item.reachability === 'mapped' ? item.ingress_port : 41194,
      local_port: item.reachability === 'mapped' ? item.local_port : 41194,
      service_port: 41194,
    }));
  payload.endpoints.push(...altEndpoints);
}

function setIpv4GateOpen(payload, sourceOverride = '') {
  const selectedSource = payload.client_sources?.ipv4?.address;
  if (!selectedSource) throw new Error('fixture is missing IPv4 client source');
  const runtimeSource = sourceOverride || selectedSource;
  const family = {
    active: true,
    family: 'ipv4',
    scope: 'wg',
    source_ip: runtimeSource,
    source_kind: 'web_candidate',
    device: 'pppoe-WAN2',
    ingress_port: 51820,
    wg_port: 51820,
    expires_in: 300,
    source_count: 1,
    authorized_sources: [runtimeSource],
    authorizations: [{source_ip: runtimeSource, source_kind: 'web_candidate', expires_in: 300}],
  };
  payload.agent.fresh = true;
  payload.agent.may_have_active_runtime = true;
  payload.agent.firewall = {
    ...payload.agent.firewall,
    active: true,
    family: 'ipv4',
    scope: 'wg',
    source_ip: runtimeSource,
    device: 'pppoe-WAN2',
    ingress_port: 51820,
    wg_port: 51820,
    expires_in: 300,
    families: {
      ipv4: family,
      ipv6: {
        active: false,
        family: 'ipv6',
        scope: '',
        source_ip: '',
        device: '',
        ingress_port: 0,
        wg_port: 0,
        expires_in: 0,
        source_count: 0,
        authorized_sources: [],
        authorizations: [],
      },
    },
  };
}

async function openScenario(browser, mutate = () => {}) {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  let activatePosts = 0;
  let failDashboard = false;

  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/gate/activate') activatePosts += 1;
  });

  await page.route('**/api/v1/dashboard', async (route) => {
    if (failDashboard) {
      await route.abort('failed');
      return;
    }
    const response = await route.fetch();
    const payload = await response.json();
    addAltWireGuard(payload);
    setIpv4GateOpen(payload);
    mutate(payload);
    await route.fulfill({response, contentType: 'application/json', body: JSON.stringify(payload)});
  });

  await page.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
  await page.waitForSelector('#endpoint-picker-trigger');
  return {
    page,
    activatePosts: () => activatePosts,
    failDashboard: () => { failDashboard = true; },
  };
}

async function chooseLanOnly(page) {
  await page.locator('#egress-mode-segment [data-egress-mode="none"]').click();
  await page.waitForFunction(() => document.querySelector('#egress-mode-segment .active')?.dataset.egressMode === 'none');
}

async function selectIpv4(page) {
  await page.locator('[data-family="ipv4"]').click();
  await page.waitForFunction(() => document.querySelector('#wg-select')?.value === 'WG_HOME');
  await page.waitForFunction(() => document.querySelector('#endpoint-select')?.value === 'ep-wan2-v4');
  await chooseLanOnly(page);
}

async function assertCloseOnly(page, expectedBadge, context) {
  if (expectedBadge) {
    await page.waitForFunction((badge) => document.querySelector('#gate-state-badge')?.textContent === badge, expectedBadge);
  }
  assert(!(await page.locator('#close-button').evaluate((node) => node.classList.contains('hidden'))), `${context}: Close must remain available`);
  assert(await page.locator('#activate-button').evaluate((node) => node.classList.contains('hidden')), `${context}: replacement Activate must remain hidden`);
  assert((await page.locator('#gate-orb').getAttribute('aria-label')) === 'Close access now', `${context}: orb must Close the active runtime`);
}

const browser = await chromium.launch({headless: true});
try {
  {
    const scenario = await openScenario(browser);
    const {page} = scenario;
    await selectIpv4(page);
    await page.waitForFunction(() => document.querySelector('#gate-state-badge')?.textContent === 'AUTHORIZED');

    assert(await page.locator('#wg-select').isVisible(), 'two WireGuard services should expose the service selector');
    await assertCloseOnly(page, 'AUTHORIZED', 'matching active profile');

    await page.locator('[data-scope="wg_ping"]').click();
    await page.evaluate(() => window.RemoteGateApp.refresh());
    await page.waitForFunction(() => document.querySelector('#gate-state')?.textContent === 'OPEN · OTHER ACCESS PATH');
    await assertCloseOnly(page, 'OPEN ELSEWHERE', 'scope mismatch');

    await page.locator('[data-scope="wg"]').click();
    await page.evaluate(() => window.RemoteGateApp.refresh());
    await page.waitForFunction(() => document.querySelector('#gate-state-badge')?.textContent === 'AUTHORIZED');

    await page.locator('#wg-select').selectOption('WG_ALT');
    await page.waitForFunction(() => document.querySelector('#endpoint-select')?.value === 'ep-wan2-v4-alt');
    await page.waitForFunction(() => document.querySelector('#gate-state')?.textContent === 'OPEN · OTHER ACCESS PATH');
    await assertCloseOnly(page, 'OPEN ELSEWHERE', 'WireGuard ingress mismatch');

    await page.locator('#wg-select').selectOption('WG_HOME');
    await page.waitForFunction(() => document.querySelector('#endpoint-select')?.value === 'ep-wan2-v4');
    await page.waitForFunction(() => document.querySelector('#gate-state-badge')?.textContent === 'AUTHORIZED');

    await page.locator('[data-family="ipv6"]').click();
    await page.waitForFunction(() => document.querySelector('#gate-state')?.textContent === 'OPEN · OTHER ACCESS PATH');
    await assertCloseOnly(page, 'OPEN ELSEWHERE', 'other-family active runtime');

    assert(scenario.activatePosts() === 0, `profile/family selection changes posted Activate (${scenario.activatePosts()})`);
    await page.close();
  }

  {
    const scenario = await openScenario(browser, (payload) => setIpv4GateOpen(payload, '198.51.100.44'));
    const {page} = scenario;
    await selectIpv4(page);
    await page.waitForFunction(() => document.querySelector('#gate-state')?.textContent === 'OPEN · OTHER ACCESS PATH');
    await assertCloseOnly(page, 'OPEN ELSEWHERE', 'same-profile different-source runtime');
    assert(scenario.activatePosts() === 0, `source mismatch posted Activate (${scenario.activatePosts()})`);
    await page.close();
  }

  {
    const scenario = await openScenario(browser);
    const {page} = scenario;
    await page.locator('[data-family="dual"]').click();
    await chooseLanOnly(page);
    await page.waitForFunction(() => document.querySelector('#gate-state')?.textContent === 'OPEN · PARTIAL ACCESS');
    await assertCloseOnly(page, 'PARTIAL OPEN', 'Dual one-family partial runtime');
    assert(scenario.activatePosts() === 0, `Dual partial state posted Activate (${scenario.activatePosts()})`);
    await page.close();
  }

  {
    let runtimeServicePort = 53127;
    const scenario = await openScenario(browser, (payload) => {
      const baseEndpoint = payload.endpoints?.find((item) => item?.id === 'ep-wan2-v4');
      if (!baseEndpoint) throw new Error('fixture is missing ep-wan2-v4');
      const baseService = payload.agent?.wireguard?.find((item) => item?.name === 'WG_HOME');
      if (!baseService) throw new Error('fixture is missing WG_HOME');
      payload.agent.wireguard.push({...baseService, name: 'WG_MAPPED', listen_port: 53127});
      const endpoint = {
        ...baseEndpoint,
        id: 'ep-wan-v4-mapped',
        wan: 'WAN',
        wireguard: 'WG_MAPPED',
        service_id: 'wg.WG_MAPPED',
      };
      payload.endpoints.push(endpoint);
      endpoint.access_method = 'mapped';
      endpoint.reachability = 'mapped';
      endpoint.device = 'pppoe-WAN';
      endpoint.ingress_port = 57470;
      endpoint.local_port = 57470;
      endpoint.service_port = 53127;
      endpoint.external_port = 45678;

      const source = payload.client_sources?.ipv4?.address;
      if (!source) throw new Error('fixture is missing IPv4 client source');
      payload.agent.firewall = {
        ...payload.agent.firewall,
        active: true,
        family: 'ipv4',
        scope: 'wg',
        source_ip: source,
        device: 'pppoe-WAN',
        ingress_port: 57470,
        wg_port: runtimeServicePort,
        expires_in: 300,
        families: {
          ...(payload.agent.firewall?.families || {}),
          ipv4: {
            active: true,
            family: 'ipv4',
            scope: 'wg',
            source_ip: source,
            source_kind: 'web_candidate',
            device: 'pppoe-WAN',
            ingress_port: 57470,
            wg_port: runtimeServicePort,
            expires_in: 300,
            source_count: 1,
            authorized_sources: [source],
            authorizations: [{source_ip: source, source_kind: 'web_candidate', expires_in: 300}],
          },
          ipv6: {
            ...(payload.agent.firewall?.families?.ipv6 || {}),
            active: false,
          },
        },
      };
    });
    const {page} = scenario;
    await page.locator('[data-family="ipv4"]').click();
    await page.waitForFunction(() => document.querySelector('#wg-select')?.value === 'WG_HOME');
    await chooseLanOnly(page);
    await page.locator('#wg-select').selectOption('WG_MAPPED');
    await page.waitForFunction(() => document.querySelector('#endpoint-select')?.value === 'ep-wan-v4-mapped');
    await page.waitForFunction(() => document.querySelector('#gate-state-badge')?.textContent === 'AUTHORIZED');
    await assertCloseOnly(page, 'AUTHORIZED', 'matching mapped ingress/service profile');

    runtimeServicePort = 53128;
    await page.evaluate(() => window.RemoteGateApp.refresh());
    await page.waitForFunction(() => document.querySelector('#gate-state')?.textContent === 'OPEN · OTHER ACCESS PATH');
    await assertCloseOnly(page, 'OPEN ELSEWHERE', 'service-port drift');
    assert(scenario.activatePosts() === 0, `service-port drift posted Activate (${scenario.activatePosts()})`);
    await page.close();
  }

  {
    const scenario = await openScenario(browser);
    const {page} = scenario;
    await selectIpv4(page);
    await page.waitForFunction(() => document.querySelector('#gate-state-badge')?.textContent === 'AUTHORIZED');
    scenario.failDashboard();
    await page.evaluate(() => window.RemoteGateApp.refresh());
    await page.waitForFunction(() => document.querySelector('#gate-state')?.textContent === 'STATUS UNKNOWN');
    assert((await page.locator('#gate-state-badge').textContent()) === 'UNKNOWN', 'failed dashboard refresh must revoke cached OPEN authority');
    assert(!(await page.locator('#close-button').evaluate((node) => node.classList.contains('hidden'))), 'failed refresh should preserve safe Close from last-known runtime hint');
    assert(await page.locator('#activate-button').isDisabled(), 'failed refresh must keep Activate disabled');
    assert(await page.locator('#gate-orb').isDisabled(), 'failed refresh must disable the Gate orb');
    assert(scenario.activatePosts() === 0, `failed dashboard refresh posted Activate (${scenario.activatePosts()})`);
    await page.close();
  }

  console.log('Browser Gate profile authority regression passed with mode-first LAN-only Internet Exit selection and zero auto-Activate.');
} finally {
  await browser.close();
}
