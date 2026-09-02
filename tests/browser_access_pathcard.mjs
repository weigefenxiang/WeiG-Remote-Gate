import { chromium } from 'playwright';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForEndpoint(page, value) {
  await page.waitForFunction((expected) => document.querySelector('#endpoint-select')?.value === expected, value);
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
    await waitForEndpoint(page, 'ep-wan2-v4');

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
    await page.waitForFunction(() => document.querySelector('#endpoint-select')?.value.startsWith('dual:'));
    const dualTriggerBlocks = await page.locator('#endpoint-picker-trigger .path-family-block').count();
    assert(dualTriggerBlocks === 2, `${width}: Dual trigger must keep two FamilyPathBlocks (${dualTriggerBlocks})`);
    await page.locator('#endpoint-picker-trigger').click();
    await page.waitForSelector('#endpoint-picker-layer.open .endpoint-option-card.selected');
    const dualPickerBlocks = await page.locator('#endpoint-picker-layer .endpoint-option-card.selected .path-family-block').count();
    assert(dualPickerBlocks === 2, `${width}: Dual picker must keep two FamilyPathBlocks (${dualPickerBlocks})`);

    assert(consoleErrors.length === 0, `${width}: browser console errors: ${consoleErrors.join(' | ')}`);
    await page.close();
  }
} finally {
  await browser.close();
}
