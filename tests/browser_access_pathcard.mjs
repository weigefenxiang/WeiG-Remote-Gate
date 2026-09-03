import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForEndpoint(page, selectId, value) {
  await page.waitForFunction(({selectId, value}) => document.querySelector(`#${selectId}`)?.value === value, {selectId, value});
}

async function assertScalarPathCard(page, triggerSelector, expectedFamily, context) {
  const trigger = await page.locator(triggerSelector).evaluate((root) => {
    const block = root?.querySelector('.path-family-block');
    const head = block?.querySelector('.path-family-head');
    const value = block?.querySelector('.path-family-value');
    return {
      blocks: root?.querySelectorAll('.path-family-block').length || 0,
      head: head?.textContent.replace(/\s+/g, ' ').trim() || '',
      value: value?.textContent.trim() || '',
    };
  });
  assert(trigger.blocks === 1, `${context}: trigger must render exactly one FamilyPathBlock (${trigger.blocks})`);
  assert(trigger.head.includes(expectedFamily), `${context}: trigger rendered the wrong family (${trigger.head})`);
  assert(trigger.value, `${context}: trigger endpoint identity is empty`);
}

async function assertScalarPicker(page, triggerSelector, expectedFamily, context) {
  await page.locator(triggerSelector).click();
  await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card.selected');
  const snapshot = await page.locator('#endpoint-picker-layer .endpoint-option-card.selected').evaluate((root) => ({
    blocks: root.querySelectorAll('.path-family-block').length,
    family: root.querySelector('.path-family-label')?.textContent?.trim() || '',
  }));
  assert(snapshot.blocks === 1, `${context}: selected picker card must render exactly one FamilyPathBlock (${snapshot.blocks})`);
  assert(snapshot.family === expectedFamily, `${context}: selected picker card rendered ${snapshot.family}`);
  await page.keyboard.press('Escape');
}

const browser = await chromium.launch({headless: true});
try {
  for (const [width, height] of [[320, 800], [1366, 768]]) {
    const page = await browser.newPage({viewport: {width, height}});
    const consoleErrors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => consoleErrors.push(String(error)));

    await page.goto('http://127.0.0.1:8765/', {waitUntil: 'networkidle'});
    await page.waitForSelector('#endpoint-picker-trigger');
    await waitForEndpoint(page, 'endpoint-select', 'ep-wan2-v4');

    const trigger = await page.evaluate(() => {
      const root = document.querySelector('#endpoint-picker-trigger');
      const block = root?.querySelector('.path-family-block');
      const head = block?.querySelector('.path-family-head');
      const value = block?.querySelector('.path-family-value');
      const rect = root?.getBoundingClientRect();
      return {
        blocks: root?.querySelectorAll('.path-family-block').length || 0,
        head: head?.textContent.replace(/\s+/g, ' ').trim() || '',
        value: value?.textContent.trim() || '',
        text: root?.textContent.replace(/\s+/g, ' ').trim() || '',
        right: rect?.right || 0,
        width: window.innerWidth,
      };
    });
    assert(trigger.blocks === 1, `${width}: single-family trigger must use one FamilyPathBlock`);
    assert(trigger.head.includes('WAN2') && trigger.head.includes('IPv4') && trigger.head.includes('Public'), `${width}: trigger first row missing WAN/family/Public: ${trigger.head}`);
    assert(!trigger.head.includes('Recommended'), `${width}: trigger must not show recommendation state`);
    assert(trigger.value === '203.0.113.18:51820', `${width}: trigger endpoint identity changed: ${trigger.value}`);
    assert(!/Private|CGNAT|NAT egress/i.test(trigger.text), `${width}: Access trigger leaked network classification: ${trigger.text}`);
    assert(trigger.right <= trigger.width + 1, `${width}: Access trigger overflows viewport`);

    const optionRows = await page.evaluate(() => {
      const option = document.querySelector('#endpoint-select')?.selectedOptions?.[0];
      return option?.dataset.pathRows ? JSON.parse(option.dataset.pathRows) : [];
    });
    assert(optionRows.length === 1, `${width}: selected Access option does not have one structured row`);
    assert(optionRows[0].family === 'IPv4' && optionRows[0].wan === 'WAN2', `${width}: structured Access row family/WAN mismatch`);
    assert(optionRows[0].role === 'Public Direct', `${width}: structured Access role mismatch: ${optionRows[0].role}`);
    assert(optionRows[0].value === '203.0.113.18:51820', `${width}: structured Access value mismatch`);

    await page.locator('#endpoint-picker-trigger').click();
    await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card[data-value="ep-wan2-v4"]');
    const picker = await page.locator('#endpoint-picker-layer .endpoint-option-card[data-value="ep-wan2-v4"]').evaluate((root) => ({
      blocks: root.querySelectorAll('.path-family-block').length,
      head: root.querySelector('.path-family-head')?.textContent.replace(/\s+/g, ' ').trim() || '',
      value: root.querySelector('.path-family-value')?.textContent.trim() || '',
      text: root.textContent.replace(/\s+/g, ' ').trim(),
    }));
    assert(picker.blocks === 1, `${width}: single-family picker card must use one FamilyPathBlock`);
    for (const token of ['IPv4', 'WAN2', 'Recommended', 'Public Direct']) {
      assert(picker.head.includes(token), `${width}: picker first row missing ${token}: ${picker.head}`);
    }
    assert(picker.value === '203.0.113.18:51820', `${width}: picker endpoint identity changed: ${picker.value}`);
    assert(!/Private|CGNAT|NAT egress/i.test(picker.text), `${width}: Access picker leaked network classification: ${picker.text}`);
    await page.keyboard.press('Escape');

    await page.locator('[data-family="dual"]').click();
    await page.waitForFunction(() => document.querySelector('#family-segment .active')?.dataset.family === 'dual');
    await waitForEndpoint(page, 'endpoint-select', 'ep-wan2-v4');
    await waitForEndpoint(page, 'access-ipv6-select', 'ep-wan2-v6');

    const dualState = await page.evaluate(() => ({
      v4: document.querySelector('#endpoint-select')?.value || '',
      v6: document.querySelector('#access-ipv6-select')?.value || '',
      v4Options: [...(document.querySelector('#endpoint-select')?.options || [])].map((option) => option.value),
      v6Options: [...(document.querySelector('#access-ipv6-select')?.options || [])].map((option) => option.value),
      visibleHeadings: [...document.querySelectorAll('.access-endpoint-control > span')].filter((node) => !node.hidden).map((node) => node.textContent.trim()),
    }));
    assert(dualState.v4 === 'ep-wan2-v4' && dualState.v6 === 'ep-wan2-v6', `${width}: Dual scalar recommendation changed (${dualState.v4}/${dualState.v6})`);
    assert(!dualState.v4Options.some((value) => String(value).startsWith('dual:')), `${width}: IPv4 selector still contains a Dual pair id`);
    assert(!dualState.v6Options.some((value) => String(value).startsWith('dual:')), `${width}: IPv6 selector still contains a Dual pair id`);
    assert(dualState.visibleHeadings.length === 1, `${width}: Dual Access added redundant visible per-family headings`);

    await assertScalarPathCard(page, '#endpoint-picker-trigger', 'IPv4', `${width}: Dual IPv4`);
    await assertScalarPathCard(page, '#access-ipv6-select-picker-trigger', 'IPv6', `${width}: Dual IPv6`);
    await assertScalarPicker(page, '#endpoint-picker-trigger', 'IPv4', `${width}: Dual IPv4`);
    await assertScalarPicker(page, '#access-ipv6-select-picker-trigger', 'IPv6', `${width}: Dual IPv6`);

    assert(consoleErrors.length === 0, `${width}: browser console errors: ${consoleErrors.join(' | ')}`);
    await page.close();
  }
} finally {
  await browser.close();
}
