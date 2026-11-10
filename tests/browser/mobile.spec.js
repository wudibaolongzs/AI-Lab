const { test, expect } = require('@playwright/test');

test.use({ viewport: { width: 390, height: 844 } });

async function openLab(page) {
  await page.goto('/');
  await expect(page.locator('#exercise-select')).toBeEnabled();
}

async function noHorizontalOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
}

test('mobile edit and judge keeps the page inside the viewport', async ({ page }) => {
  await openLab(page);
  await page.locator('#code').fill('def average(nums):\n    return 0');
  await page.locator('#run').click();
  await expect(page.locator('#cases li')).toHaveCount(4);
  expect(await noHorizontalOverflow(page)).toBe(true);
  await expect(page.locator('#run')).toBeInViewport();
});

test('mobile theme choice survives a reload', async ({ page }) => {
  await openLab(page);
  const before = await page.locator('html').getAttribute('data-theme');
  await page.locator('#theme-toggle').click();
  const chosen = await page.locator('html').getAttribute('data-theme');
  expect(chosen).not.toBe(before);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', chosen);
});

test('mobile drafts survive reload and exercise switching', async ({ page }) => {
  await openLab(page);
  await page.locator('#code').fill('def average(nums):\n    return 1234');
  await page.reload();
  await expect(page.locator('#code')).toHaveValue('def average(nums):\n    return 1234');
  await page.locator('#exercise-select').selectOption({ index: 1 });
  await page.locator('#exercise-select').selectOption('average');
  await expect(page.locator('#code')).toHaveValue('def average(nums):\n    return 1234');
});

test('mobile hint expands with its source badge', async ({ page }) => {
  await page.route('**/api/hint', route => route.fulfill({ json: {
    source: 'agentarts', hint: '移动端提示只在视口内展开。', case_id: 'C01', request_id: 'mobile-fixture'
  } }));
  await openLab(page);
  await page.locator('#run').click();
  await page.locator('#reveal').click();
  await expect(page.locator('#hint-list li')).toHaveCount(1);
  await expect(page.locator('#hint-list .tag')).toHaveText('AgentArts');
  expect(await noHorizontalOverflow(page)).toBe(true);
});

test('a shorter viewport, like an open soft keyboard, keeps controls reachable', async ({ page }) => {
  await openLab(page);
  await page.setViewportSize({ width: 390, height: 420 });
  await page.locator('#code').fill('def average(nums):\n    return sum(nums) / 3');
  await page.locator('#run').scrollIntoViewIfNeeded();
  await page.locator('#run').click();
  await expect(page.locator('#cases li')).toHaveCount(4);
  await page.locator('#reveal').scrollIntoViewIfNeeded();
  await expect(page.locator('#reveal')).toBeInViewport();
  expect(await noHorizontalOverflow(page)).toBe(true);
});