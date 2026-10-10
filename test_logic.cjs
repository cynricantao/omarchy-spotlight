const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = path.join(__dirname, 'Logic.js');
assert.ok(fs.existsSync(source), 'Spotlight response controller must exist');
const logic = vm.createContext({});
vm.runInContext(fs.readFileSync(source, 'utf8').replace(/^\.pragma library\s*/, ''), logic);
// Only the response to the currently visible query can become actionable.
assert.equal(logic.acceptResponse({query:'old'}, 'new', true), false);
assert.equal(logic.acceptResponse({query:'new'}, 'new', false), false);
assert.equal(logic.acceptResponse({query:'new'}, 'new', true), true);
assert.equal(logic.acceptResponse(null, 'new', true), false);
console.log('PASS: stale / closed / current / malformed response gating');
assert.equal(typeof logic.pointerMoved, 'function', 'Hover must distinguish actual pointer motion from a new result under a stationary pointer');
assert.equal(logic.pointerMoved(-1,-1,100,200), false);
assert.equal(logic.pointerMoved(100,200,100,200), false);
assert.equal(logic.pointerMoved(100,200,100.1,200.1), false);
assert.equal(logic.pointerMoved(100,200,103,200), true);
console.log('PASS: initial/stationary/subpixel pointer cannot steal keyboard selection');
assert.equal(typeof logic.sectionize, 'function', 'reference design requires grouped results');
const sample=[{id:'home',kind:'action'},{id:'a',kind:'app'},{id:'f',kind:'file'},{id:'b',kind:'app'},{id:'w',kind:'web'},{id:'ai',kind:'ai'}];
const grouped=logic.sectionize(sample,'All');
assert.equal(JSON.stringify(grouped.sections.map(s=>s.title)),JSON.stringify(['Top Result','Apps','Files','Web','AI']));
assert.equal(JSON.stringify(grouped.items.map(x=>x.id)),JSON.stringify(['home','a','b','f','w','ai']));
assert.equal(JSON.stringify(grouped.sections.flatMap(s=>s.rows.map(x=>x.index))),JSON.stringify([0,1,2,3,4,5]));
assert.equal(logic.sectionize([], 'Files').sections.length,0);
assert.equal(logic.sectionize(sample.slice(1,2),'Apps').sections[0].layout,'tiles');
assert.equal(logic.linkUrl('github'),'https://github.com/');
assert.equal(logic.linkUrl('https://untrusted.invalid'),'');
assert.equal(logic.quickLinks().length,3);
console.log('PASS: grouped visual order preserves exact action indices; web links allowlisted');
assert.equal(typeof logic.customAiPayload, 'function', 'custom CLI editor needs a literal-argv parser');
const custom=logic.customAiPayload('["my-ai","--prompt={prompt}","literal $value"]');
assert.equal(JSON.stringify(custom),JSON.stringify({provider:'custom',custom_argv:['my-ai','--prompt={prompt}','literal $value']}));
for (const bad of ['not json','{}','[]','["{prompt}","x"]','["ai",123,"{prompt}"]','["ai","no prompt"]','["ai","{prompt}","{prompt}"]']) {
  assert.throws(()=>logic.customAiPayload(bad));
}
console.log('PASS: custom CLI editor accepts argv JSON, rejects malformed templates, preserves literal tokens');
