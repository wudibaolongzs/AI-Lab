
const {test,expect}=require('@playwright/test');
test('catalog filters source, pages and preserves current draft',async({page})=>{
  await page.goto('/');
  await expect(page.locator('#exercise-select')).toBeEnabled();
  await page.locator('#code').fill('def average(nums):\n    return 123');
  await page.locator('#catalog-source').selectOption('Exercism Python');
  await expect(page.locator('#catalog-status')).toHaveText('共 20 道题');
  await expect(page.locator('#catalog-items article')).toHaveCount(12);
  await page.locator('#catalog-next').click();
  await expect(page.locator('#catalog-items article')).toHaveCount(8);
  await expect(page.locator('#code')).toHaveValue('def average(nums):\n    return 123');
  await page.locator('#catalog-items button').first().click();
  await expect(page.locator('#exercise-select')).not.toHaveValue('average');
  await page.locator('#exercise-select').selectOption('average');
  await expect(page.locator('#code')).toHaveValue('def average(nums):\n    return 123');
});
test('open source string task runs and explicitly lacks transfer',async({page})=>{
  await page.goto('/');
  const items=await (await page.request.get('/api/exercises')).json();
  const item=items.find(p=>p.id.includes('reverse'));
  expect(item).toBeTruthy();
  await expect(page.locator('#exercise-select')).toBeEnabled();
  await page.locator('#exercise-select').selectOption(item.id);
  await page.locator('#code').fill(item.signature+'\n    return '+item.parameters[0].name+'[::-1]');
  await page.locator('#run').click();
  await expect(page.locator('#result-label')).toContainText(item.id ? '/' : 'passed');
  await expect(page.locator('#learning-heading')).toContainText('暂未配置理解验证');
  await expect(page.locator('#learning-submit')).toBeDisabled();
  await expect(page.locator('#exercise-source')).toContainText('MIT');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
