const {test,expect}=require('@playwright/test');
async function setup(page,enabled=false){
 await page.route('**/api/classroom/teacher',r=>r.fulfill({json:{class_id:'A',tasks:[],help:[]}}));
 await page.route('**/api/materials',r=>r.fulfill({json:{drafts:[],ocr_enabled:enabled}}));
 await page.goto('/teacher');
 await page.locator('#credential').fill('teacher-A');await page.locator('#connect').click();
 await expect(page.locator('#materials')).toBeVisible();
}
test('text drafts require rights and export requires validation and manual review',async({page})=>{
 let created, exported=0, saved;
 await page.route('**/api/materials/text',async r=>{
  created=r.request().postDataJSON();
  await r.fulfill({json:{id:'draft-1',title:created.title,text:created.text,source_note:created.source_note,pack:null,state:'draft'}});
 });
 await page.route('**/api/materials/save',async r=>{saved=r.request().postDataJSON();await r.fulfill({json:{ok:true}});});
 await page.route('**/api/materials/validate',r=>r.fulfill({json:{valid:true}}));
 await page.route('**/api/materials/export',async r=>{
  expect(r.request().postDataJSON()).toEqual({id:'draft-1',review_confirmed:true});exported++;
  await r.fulfill({json:{pack:saved.pack}});
 });
 await setup(page);
 await expect(page.locator('#mat-submit-photo')).toBeDisabled();
 await page.locator('#mat-title').fill('Material');
 await page.locator('#mat-text').fill('<img src=x onerror="window.leaked=true">');
 await page.locator('#mat-submit-text').click();
 await expect(page.locator('#mat-message')).toContainText('来源');
 expect(created).toBeUndefined();
 await page.locator('#mat-source').fill('Owned textbook');
 await page.locator('#mat-rights').check();await page.locator('#mat-submit-text').click();
 await expect(page.locator('#mat-pack')).toHaveValue(/schema_version/);
 expect(created.rights_confirmed).toBe(true);
 expect(await page.evaluate(()=>window.leaked)).toBeUndefined();
 const template=JSON.parse(await page.locator('#mat-pack').inputValue());
 expect(template.problems[0].cases).toEqual([]);
 expect(template.problems[0].reference_code).toBe('');
 await expect(page.locator('#mat-export')).toBeDisabled();
 await page.locator('#mat-validate').click();
 await expect(page.locator('#mat-message')).toContainText('校验通过');
 await expect(page.locator('#mat-export')).toBeDisabled();
 await page.locator('#mat-review').check();
 const download=page.waitForEvent('download');await page.locator('#mat-export').click();await download;
 expect(exported).toBe(1);
 await page.locator('#mat-text').fill('Changed');
 await expect(page.locator('#mat-export')).toBeDisabled();
});
test('photo consent, raw base64 and logout discard a late response',async({page})=>{
 let held, calls=0;
 await page.route('**/api/materials/ocr',r=>{held=r;calls++;});
 await setup(page,true);
 await page.locator('#mat-title').fill('Private photo');
 await page.locator('#mat-source').fill('Own materials');await page.locator('#mat-rights').check();
 await page.locator('#mat-photo').setInputFiles({name:'scan.png',mimeType:'image/png',buffer:Buffer.from([137,80,78,71])});
 await page.locator('#mat-submit-photo').click();
 await expect(page.locator('#mat-message')).toContainText('百度');
 expect(calls).toBe(0);
 await page.locator('#mat-upload').check();await page.locator('#mat-submit-photo').click();
 await expect.poll(()=>calls).toBe(1);
 expect(held.request().postDataJSON().image).toBe('iVBORw==');
 expect(held.request().postDataJSON().upload_confirmed).toBe(true);
 await expect(page.locator('#mat-submit-photo')).toBeDisabled();
 await page.locator('#logout').click();
 await held.fulfill({json:{id:'private',title:'Late secret',text:'private text',source_note:'private',pack:null}});
 await page.waitForLoadState('networkidle');
 await expect(page.locator('#materials')).toBeHidden();
 for(const id of ['mat-title','mat-text','mat-source','mat-pack','mat-photo','mat-txt'])await expect(page.locator('#'+id)).toHaveValue('');
 await expect(page.locator('#mat-upload')).not.toBeChecked();
 await expect(page.locator('#mat-rights')).not.toBeChecked();
 expect(await page.evaluate(()=>localStorage.length)).toBe(0);
});

test('TXT decoding that completes after logout cannot restore private text',async({page})=>{
 await setup(page);
 await page.evaluate(()=>{
  window.releaseMaterialFile=null;
  File.prototype.arrayBuffer=function(){return new Promise(resolve=>{window.releaseMaterialFile=()=>resolve(new TextEncoder().encode('private local text').buffer);});};
 });
 await page.locator('#mat-txt').setInputFiles({name:'notes.txt',mimeType:'text/plain',buffer:Buffer.from('private local text')});
 await expect.poll(()=>page.evaluate(()=>typeof window.releaseMaterialFile)).toBe('function');
 await page.locator('#logout').click();
 await page.evaluate(()=>window.releaseMaterialFile());
 await expect(page.locator('#mat-text')).toHaveValue('');
 await expect(page.locator('#materials')).toBeHidden();
});

test('changing the selected photo requires fresh upload consent',async({page})=>{
 await setup(page,true);
 const photo={name:'first.png',mimeType:'image/png',buffer:Buffer.from([137,80,78,71])};
 await page.locator('#mat-photo').setInputFiles(photo);
 await page.locator('#mat-upload').check();
 await page.locator('#mat-photo').setInputFiles({...photo,name:'second.png'});
 await expect(page.locator('#mat-upload')).not.toBeChecked();
});
