const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

for (const [hash, page] of [['#module1', 'models'], ['#module2', 'quotas'], ['#module3', 'credits']]) {
  const events = {};
  const location = {hash};
  const context = vm.createContext({
    location,
    document: {addEventListener() {}, getElementById: () => ({innerHTML: ''})},
    localStorage: {getItem: () => null},
    matchMedia: () => ({matches: true}),
    window: {addEventListener: (name, fn) => { events[name] = fn; }, scrollTo() {}},
    renderModels: () => '', renderQuotas: () => '', renderCredits: () => '',
  });
  for (const name of ['core', 'actions']) {
    vm.runInContext(fs.readFileSync(`apps/web/shared/${name}.js`, 'utf8'), context);
  }
  const evaluate = source => vm.runInContext(source, context);
  assert.equal(evaluate('ui.page'), page);
  assert.equal(evaluate('ui.sidebarOpen'), true);
  evaluate("updatePage('quotas')");
  assert.equal(evaluate('ui.sidebarOpen'), true);
  evaluate("dispatch('tab', {dataset: {page: 'quotas', tab: 'lookup'}})");
  assert.equal(evaluate('ui.sidebarOpen'), true);
  evaluate("dispatch('toggle-sidebar', {dataset: {}})");
  evaluate("updatePage('credits')");
  assert.equal(evaluate('ui.sidebarOpen'), false);
  location.hash = '#module2';
  events.hashchange();
  assert.equal(evaluate('ui.page'), 'quotas');
  assert.equal(evaluate('ui.sidebarOpen'), false);
  location.hash = '#module3';
  events.hashchange();
  assert.equal(evaluate('ui.page'), 'credits');
  assert.equal(evaluate('ui.sidebarOpen'), false);
}
console.log('PASS: direct desktop routes, tabs, module navigation and browser hash history.');
