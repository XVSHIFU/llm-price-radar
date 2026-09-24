// Syntax, embedded-data consistency and the regression-prone pure UI operations.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('index.html', 'utf8');
for (const [, attrs, body] of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
  if (!attrs.includes('application/json')) new vm.Script(body);
}
const embedded = id => JSON.parse(html.match(new RegExp(`<script id="${id}" type="application/json">([\\s\\S]*?)</script>`))[1]);
assert.deepEqual(embedded('model-data'), JSON.parse(fs.readFileSync('data.json', 'utf8')));
assert.deepEqual(embedded('plan-data'), JSON.parse(fs.readFileSync('plans.json', 'utf8')));
const lines = html.split(/\r?\n/);
const nodes = {};
const $ = key => nodes[key] ??= {value: '', addEventListener(type, fn) { this[type] = fn; }};
const context = vm.createContext({DATA: embedded('model-data'), PLANS: embedded('plan-data'), $, assert,
  CSS: {escape: v => v}, document: {querySelector: () => null}, save() {}, notify() {}, exportCSV() {}});
const starts = ['let lastFo=', 'const mode=', 'const current=', 'const allItems=', 'const getItem=',
  'const isModel=', 'function draft(', 'const regionOf=', 'function resetFilters(', 'function toggleGroup(',
  'function getFiltered(', 'const revalidateCompare=', "$('#search').addEventListener('input',e=>{state.searchFold",
  "$('#provider').onchange"];
vm.runInContext(starts.map(prefix => {
  const line = lines.find(x => x.startsWith(prefix));
  assert.ok(line, `Missing UI function ${prefix}`);
  return line;
}).join('\n') + '\nfunction render(){}', context);
vm.runInContext(`
state.view='plans'; state.sort='price';
for(const currency of ['USD','CNY']) {
  const prices=getFiltered().filter(x=>curCur(x)===currency).map(x=>planCur(x).price);
  assert.ok(prices.every((p,i)=>!i||prices[i-1]<=p));
}
state.compare=['minimax-plus','codex-plus']; state.planRegion.MiniMax='国内';
revalidateCompare(); assert.equal(state.compare.join(','),'minimax-plus');
state.planRegion['阿里云']='国内';
assert.equal(dispCur(PLANS.plans.filter(x=>x.provider==='阿里云')),'CNY/USD');
state.view='models'; state.sort='default';
$('#search').input({target:{value:'MiniMax'}}); toggleGroup('models:MiniMax');
assert.equal(state.searchFold['models:MiniMax'],true);
resetFilters(); $('#search').input({target:{value:'MiniMax M2.7'}});
assert.ok(!state.searchFold['models:MiniMax']);
`, context);
console.log('Frontend syntax, embedded data and regression checks passed.');
