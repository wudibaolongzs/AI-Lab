const { test, expect } = require('@playwright/test');
const correctCode = 'def average(nums):\n    return sum(nums) / len(nums)';
test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#exercise-select')).toBeEnabled();
});
test('numeric transfer is independent of prose and invalidated on edits', async ({ page }) => {
  await page.route('**/api/learning/challenge?*', route => route.fulfill({ json: { exercise_id: 'average', question_id: 'transfer', question: '计算新输入的平均数', answer_type: 'number' } }));
  await page.route('**/api/learning/verify', async route => {
    const body = route.request().postDataJSON();
    await route.fulfill({ json: { correct: body.answer === 7, explanation_recorded: Boolean(body.explanation), message: body.answer === 7 ? '数值正确' : '请再思考' } });
  });
  await page.locator('#code').fill(correctCode);
  await page.locator('#run').click();
  await expect(page.locator('#learning-submit')).toBeEnabled();
  await page.locator('#learning-explanation').fill('看起来很正确的长解释');
  await page.locator('#learning-answer').fill('1');
  await page.locator('#learning-submit').click();
  await expect(page.locator('#learning-message')).toHaveText('请再思考');
  await expect(page.locator('#learning-heading')).toContainText('待完成');
  await page.locator('#learning-answer').fill('7');
  await page.locator('#learning-submit').click();
  await expect(page.locator('#learning-heading')).toHaveText('变式验证通过');
  const learning = await page.evaluate(() => JSON.parse(localStorage.getItem('ai-lab.v1.exercise.average')).learning);
  expect(learning.attempt_count).toBe(2);
  expect(learning.first_correct).toBe(false);
  expect(learning.explanation).toBe('看起来很正确的长解释');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#export-records').click();
  const download = await downloadPromise;
  await page.locator('#import-records').setInputFiles(await download.path());
  await expect(page.locator('#records-message')).toContainText('已导入');
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('ai-lab.v1.exercise.average')).learning.explanation)).toBe('看起来很正确的长解释');
  await page.locator('#code').fill(correctCode + '\n');
  await expect(page.locator('#learning')).toBeHidden();
});
test('feedback persists and malformed import leaves storage intact', async ({ page }) => {
  await page.route('**/api/hint', route => route.abort());
  await page.locator('#run').click();
  await page.locator('#reveal').click();
  await page.getByRole('button', { name: '有帮助', exact: true }).click();
  const before = await page.evaluate(() => localStorage.getItem('ai-lab.v1.exercise.average'));
  expect(JSON.parse(before).feedback[0].choice).toBe('有帮助');
  await page.locator('#import-records').setInputFiles({ name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ version: 1, records: [{ id: 'unknown' }] })) });
  await expect(page.locator('#records-message')).toContainText('导入失败');
  expect(await page.evaluate(() => localStorage.getItem('ai-lab.v1.exercise.average'))).toBe(before);
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#export-records').click();
  const download = await downloadPromise;
  await page.reload();
  await expect(page.locator('#exercise-select')).toBeEnabled();
  await page.locator('#import-records').setInputFiles(await download.path());
  await expect(page.locator('#records-message')).toContainText('已导入');
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('ai-lab.v1.exercise.average')).feedback[0].choice)).toBe('有帮助');
});

test('import cannot replace draft while a grading request is pending', async ({ page }) => {
  let release;
  const held = new Promise(resolve => { release = resolve; });
  await page.route('**/api/check', async route => {
    await held;
    await route.fulfill({ json: { status: 'failed', passed: 0, total: 1, cases: [], hints: ['再想一想'] } });
  });
  await page.locator('#code').fill('current draft');
  const before = await page.evaluate(() => localStorage.getItem('ai-lab.v1.exercise.average'));
  await page.locator('#run').click();
  await expect(page.locator('#import-records')).toBeDisabled();
  // Dispatch a synthetic change to exercise the event handler's race guard as well.
  await page.evaluate(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([JSON.stringify({ version: 1, records: [{ id: 'average', draft: 'imported draft', passed: true, attempts: [], feedback: [], learning: null }] })], 'records.json', { type: 'application/json' }));
    const input = document.querySelector('#import-records');
    input.files = transfer.files;
    input.dispatchEvent(new Event('change'));
  });
  await expect(page.locator('#records-message')).toContainText('测试运行中');
  expect(await page.evaluate(() => localStorage.getItem('ai-lab.v1.exercise.average'))).toBe(before);
  release();
  await expect(page.locator('#run')).toBeEnabled();
  await expect(page.locator('#code')).toHaveValue('current draft');
});
