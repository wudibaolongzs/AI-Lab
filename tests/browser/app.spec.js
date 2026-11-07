const { test, expect } = require('@playwright/test');
test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#exercise-select')).toBeEnabled();
});
test('theme persists after reload', async ({ page }) => {
  const before = await page.locator('html').getAttribute('data-theme');
  await page.locator('#theme-toggle').click();
  const chosen = await page.locator('html').getAttribute('data-theme');
  expect(chosen).not.toBe(before);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', chosen);
});
test('mobile layout fits viewport and theme stays visible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('#theme-toggle')).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
test('Ctrl+Enter submits the current exercise', async ({ page }) => {
  await page.locator('#code').focus();
  const submitted = page.waitForRequest('**/api/check');
  await page.locator('#code').press('Control+Enter');
  await submitted;
  await expect(page.locator('#cases li')).toHaveCount(4);
  await expect(page.locator('#reveal')).toBeVisible();
});
test('hint network failure falls back to local rules', async ({ page }) => {
  await page.route('**/api/hint', route => route.abort('failed'));
  await page.locator('#run').click();
  await page.locator('#reveal').click();
  await expect(page.locator('#hint-list li')).toHaveCount(1);
  await expect(page.locator('#hint-list .tag')).toHaveText('本地规则');
  await expect(page.locator('#reveal')).toBeEnabled();
});
test('drafts survive switching exercises', async ({ page }) => {
  await page.locator('#code').fill('def average(nums):\n    return 123');
  await page.locator('#exercise-select').selectOption({ index: 1 });
  await page.locator('#code').fill('second exercise draft');
  await page.locator('#exercise-select').selectOption('average');
  await expect(page.locator('#code')).toHaveValue('def average(nums):\n    return 123');
  await page.locator('#exercise-select').selectOption({ index: 1 });
  await expect(page.locator('#code')).toHaveValue('second exercise draft');
});
test('wrong average yields hint then correction passes four cases', async ({ page }) => {
  await page.locator('#run').click();
  await expect(page.locator('#reveal')).toBeVisible();
  await page.locator('#reveal').click();
  await expect(page.locator('#hint-list li')).toHaveCount(1);
  await page.locator('#code').fill('def average(nums):\n    return sum(nums) / len(nums)');
  await page.locator('#run').click();
  await expect(page.locator('#result-label')).toContainText('4/4');
});
for (const [source, badge] of [['tencent', '腾讯云'], ['deepseek', 'DeepSeek'], ['agentarts', 'AgentArts']]) {
  test(`intercepted ${source} hint shows source badge`, async ({ page }) => {
    await page.route('**/api/hint', route => route.fulfill({ json: {
      source, hint: 'fixture hint only', case_id: 'C01', request_id: 'browser-fixture'
    } }));
    await page.locator('#run').click();
    await page.locator('#reveal').click();
    await expect(page.locator('#hint-list .tag')).toHaveText(badge);
  });
}
test('switching exercise aborts stale hint', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/api/hint', async route => {
    await gate;
    await route.fulfill({ json: { source: 'tencent', hint: 'STALE_HINT', case_id: 'C01' } }).catch(() => {});
  });
  await page.locator('#run').click();
  const requested = page.waitForRequest('**/api/hint');
  await page.locator('#reveal').click();
  const request = await requested;
  const finished = page.waitForEvent('requestfailed', { predicate: r => r === request });
  await page.locator('#exercise-select').selectOption({ index: 1 });
  await finished;
  release();
  await expect(page.locator('#hint-list li')).toHaveCount(0);
  await expect(page.locator('#hints')).toBeHidden();
  await page.locator('#exercise-select').selectOption('average');
  await expect(page.locator('#hint-list li')).toHaveCount(0);
});
