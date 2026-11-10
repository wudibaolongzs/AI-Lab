const { test, expect } = require('@playwright/test');
const correctCode = 'def average(nums):\n    return sum(nums) / len(nums)';

async function openLab(page) {
  await page.goto('/');
  await expect(page.locator('#exercise-select')).toBeEnabled();
}

test('first pass pops a glass cheer card that stays dismissible', async ({ page }) => {
  await openLab(page);
  await page.locator('#code').fill(correctCode);
  await page.locator('#run').click();
  await expect(page.locator('#cheer')).toBeVisible();
  await expect(page.locator('#cheer-emoji')).toHaveText('🎉');
  await expect(page.locator('#cheer-title')).toContainText('通过');
  await page.locator('#cheer-close').click();
  await expect(page.locator('#cheer')).toBeHidden();
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('ai-lab.v1.motivation')));
  expect(stored.days).toHaveLength(1);
  expect(stored.prompts).toEqual({});
});

test('a later pass after mistakes praises persistence', async ({ page }) => {
  await openLab(page);
  await page.locator('#code').fill(correctCode);
  await page.locator('#run').click();
  await expect(page.locator('#cheer')).toBeVisible();
  await page.locator('#cheer-close').click();
  await page.locator('#code').fill('def average(nums):\n    return 0');
  await page.locator('#run').click();
  await page.locator('#code').fill(correctCode);
  await page.locator('#run').click();
  await expect(page.locator('#cheer-title')).toHaveText('坚持有回报');
  await expect(page.locator('#cheer-body')).toContainText('节奏');
});

test('two cartoon study buddies flank wide layouts and leave narrow ones clean', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 820 });
  await openLab(page);
  await expect(page.locator('.mascot--left')).toBeVisible();
  await expect(page.locator('.mascot--right')).toBeVisible();
  await expect(page.locator('.mascot--left .mascot-bubble')).toHaveText('加油，慢慢来！');
  await expect(page.locator('.mascot--right .mascot-bubble')).toHaveText('你可以的！');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.mascot--left')).toBeHidden();
  await expect(page.locator('.mascot--right')).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('a three day streak celebrates once and is not repeated on reload', async ({ page }) => {
  await page.route('**/api/check', route => route.fulfill({
    json: { status: 'failed', passed: 0, total: 4, cases: [], hints: ['先检查分子'] },
  }));
  await openLab(page);
  await page.evaluate(() => {
    const pad = value => String(value).padStart(2, '0');
    const key = date => [date.getFullYear(), pad(date.getMonth() + 1), pad(date.getDate())].join('-');
    const days = [2, 1].map(offset => {
      const date = new Date();
      date.setDate(date.getDate() - offset);
      return key(date);
    });
    localStorage.setItem('ai-lab.v1.motivation', JSON.stringify({ days, prompts: {} }));
  });
  await page.reload();
  await expect(page.locator('#exercise-select')).toBeEnabled();
  await page.locator('#run').click();
  await expect(page.locator('#cheer-emoji')).toHaveText('🔥');
  await expect(page.locator('#cheer-title')).toHaveText('连续学习 3 天');
  await page.reload();
  await expect(page.locator('#exercise-select')).toBeEnabled();
  await page.waitForTimeout(2000);
  await expect(page.locator('#cheer')).toBeHidden();
});