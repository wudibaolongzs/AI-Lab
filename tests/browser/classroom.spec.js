const { test, expect } = require('@playwright/test');
const view = (id, question) => ({ class_id: id, tasks: [], help: [{ id: id + '-help', student_id: id, exercise_id: 'average', question, reply: '', created_at: '' }], counts: {tasks: 0, help_requests: 1, unanswered: 1} });
async function login(page, credential) {
  await page.locator('#credential').fill(credential);
  await page.locator('#connect').click();
}
test('old teacher refresh never exposes class A after logout and class B login', async ({ page }) => {
  let held, hold = false;
  await page.route('**/api/classroom/teacher', async route => {
    const auth = route.request().headers()['x-classroom-token'];
    if (auth === 'session-A' && hold) { held = route; return; }
    await route.fulfill({json: auth === 'session-A' ? view('A','initial A question') : view('B','private B question')});
  });
  await page.goto('/teacher');
  await login(page, 'session-A');
  await expect(page.locator('#status')).toHaveText('班级：A');
  hold = true;
  await page.locator('#refresh').click();
  await expect.poll(() => Boolean(held)).toBe(true);
  await page.locator('#logout').click();
  await login(page, 'session-B');
  await expect(page.locator('#status')).toHaveText('班级：B');
  await held.fulfill({json: view('A','late private A question')});
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#status')).toHaveText('班级：B');
  await expect(page.locator('#queue')).toContainText('private B question');
  await expect(page.locator('#queue')).not.toContainText('late private A question');
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
});
test('old reply failure does not overwrite new session status', async ({ page }) => {
  let held;
  await page.route('**/api/classroom/teacher', route => route.fulfill({json: view(route.request().headers()['x-classroom-token'].endsWith('session-A') ? 'A' : 'B', 'question')}));
  await page.route('**/api/classroom/reply', route => { held = route; });
  await page.goto('/teacher');
  await login(page, 'session-A');
  await page.getByLabel('教师回复').fill('reply A');
  await page.getByRole('button', {name:'保存回复'}).click();
  await expect.poll(() => Boolean(held)).toBe(true);
  expect(held.request().headers()['x-classroom-token']).toBe('session-A');
  await page.locator('#logout').click();
  await login(page, 'session-B');
  await expect(page.locator('#status')).toHaveText('班级：B');
  await held.fulfill({status: 503, json: {error:'late A failure'}});
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#status')).toHaveText('班级：B');
});

test('student explicitly submits a manual help request', async ({page}) => {
  let submitted;
  await page.route('**/api/classroom/student', r=>r.fulfill({json:{class_id:'A',tasks:[],help:[]}}));
  await page.route('**/api/classroom/help', async r=>{
    submitted=r.request().postDataJSON();
    expect(r.request().headers()['x-classroom-token']).toBe('student-token');
    await r.fulfill({json:{id:'help-1'}});
  });
  await page.goto('/teacher');
  await page.locator('#role').selectOption('student');
  await login(page,'student-token');
  await expect(page.locator('#ask')).toBeVisible();
  await page.locator('#ask-submission').fill('attempt-1');
  await page.locator('#ask-question').fill('Why this result?');
  await page.locator('#ask-send').click();
  await expect.poll(()=>submitted?.source).toBe('manual');
  expect(submitted.code).toBeUndefined();
});
