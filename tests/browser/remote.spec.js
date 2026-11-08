const {test,expect}=require('@playwright/test');
const remote={id:'remote-fixture',title:'Remote fixture (simulated)',engine:'luogu_remote',tags:['fixture'],source:{name:'Luogu fixture (simulated)',url:'https://www.luogu.com.cn/problem/P1001'},remote:{pid:'P1001',languages:['python3/c','cxx/17/gcc'],statement_available:false}};
async function setup(page,enabled=true){
  await page.route('**/api/exercises',async route=>{const response=await route.fetch();const items=await response.json();await route.fulfill({json:[items[0],remote]});});
  await page.route('**/api/remote/config',route=>route.fulfill({json:{enabled,reason:enabled?'enabled':'not_configured'}}));
  await page.goto('/');await expect(page.locator('#exercise-select')).toBeEnabled();
  await page.locator('#exercise-select').selectOption(remote.id);
}
async function authorize(page){await page.locator('#remote-token').fill('fixture-secret');await page.locator('#remote-confirm').check();}
test('remote disabled never submits locally or remotely',async({page})=>{
  let checks=0;page.on('request',r=>{if(r.url().endsWith('/api/check'))checks++;});
  await setup(page,false);await authorize(page);
  await expect(page.locator('#remote-submit')).toBeDisabled();await expect(page.locator('#run')).toBeHidden();
  await page.locator('#code').press('Control+Enter');expect(checks).toBe(0);
  await expect(page.locator('#hints')).toBeHidden();await expect(page.locator('#learning')).toBeHidden();
  await expect(page.locator('#exercise-source a')).toHaveAttribute('href',remote.source.url);
});
test('language drafts persist independently and credential never enters storage or export',async({page})=>{
  await setup(page);await page.locator('#remote-token').fill('fixture-secret');
  await page.locator('#code').fill('print(11)');await page.locator('#remote-language').selectOption('cxx/17/gcc');
  await page.locator('#code').fill('int main() {}');await page.locator('#remote-language').selectOption('python3/c');
  await expect(page.locator('#code')).toHaveValue('print(11)');
  const storage=await page.evaluate(()=>JSON.stringify({...localStorage}));expect(storage).not.toContain('fixture-secret');
  const downloadPromise=page.waitForEvent('download');await page.locator('#export-records').click();const download=await downloadPromise;
  const fs=require('node:fs');const exported=fs.readFileSync(await download.path(),'utf8');expect(exported).not.toContain('fixture-secret');expect(exported).toContain('int main() {}');
  await page.reload();await expect(page.locator('#remote-token')).toHaveValue('');await expect(page.locator('#code')).toHaveValue('print(11)');
});
test('upload acknowledgment resets and network retry retains logical id',async({page})=>{
  const bodies=[];await page.route('**/api/remote/submissions',async route=>{bodies.push(route.request().postDataJSON());expect(route.request().headers()['x-classroom-token']).toBe('fixture-secret');if(bodies.length===1)await route.abort();else await route.fulfill({json:{id:'simulated-1',status:'completed',source:'luogu',result:{verdict:'Accepted'}}});});
  await setup(page);await authorize(page);await page.locator('#remote-submit').click();await expect(page.locator('#remote-submit')).toBeDisabled();
  await page.locator('#remote-confirm').check();await page.locator('#remote-submit').click();await expect(page.locator('#remote-result')).toContainText('Accepted');
  expect(bodies[0].client_submission_id).toBe(bodies[1].client_submission_id);expect(bodies[1].upload_confirmed).toBe(true);
  await expect(page.locator('#learning')).toBeHidden();expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('ai-lab.v1.exercise.remote-fixture')||'{"passed":false}').passed)).toBe(false);
});
test('stale submission response cannot replace switched exercise or logged-out status',async({page})=>{
  let held;await page.route('**/api/remote/submissions',route=>{held=route;});
  await setup(page);await authorize(page);await page.locator('#remote-submit').click();await expect.poll(()=>!!held).toBe(true);
  await page.locator('#remote-logout').click();await held.fulfill({json:{id:'simulated-old',status:'completed',result:{verdict:'STALE'}}});
  await expect(page.locator('#remote-result')).toHaveText('');await expect(page.locator('#remote-token')).toHaveValue('');
  await page.locator('#exercise-select').selectOption({index:0});await expect(page.locator('#remote-panel')).toBeHidden();
});
test('old polling response is discarded after code change and result remains text',async({page})=>{
  let held;await page.route('**/api/remote/submissions',route=>route.fulfill({json:{id:'simulated-poll',status:'judging',next_poll_seconds:2}}));
  await page.route('**/api/remote/submissions/simulated-poll',route=>{held=route;});
  await setup(page);await authorize(page);await page.locator('#remote-submit').click();await expect(page.locator('#remote-refresh')).toBeEnabled();await page.locator('#remote-refresh').click();await expect.poll(()=>!!held).toBe(true);
  await page.locator('#code').fill('print(123)');await held.fulfill({json:{id:'simulated-poll',status:'completed',result:{verdict:'<img src=x onerror=alert(1)>'}}});
  await expect(page.locator('#remote-result')).toHaveText('');await expect(page.locator('#remote-result img')).toHaveCount(0);
});
