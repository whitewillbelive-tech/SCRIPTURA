const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const ts = require('typescript');

// Load the real TypeScript module as CommonJS, retaining its actual fixture import.
const filename = path.resolve(__dirname, '../src/lib/demo.ts');
const source = fs.readFileSync(filename, 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText;
const moduleObject = { exports: {} };
vm.runInNewContext('(function(require,module,exports){' + js + '\n})', { console }, { filename })(createRequire(filename), moduleObject, moduleObject.exports);
const { permitsContent } = moduleObject.exports;
for (const action of ['store', 'embed', 'redistribute']) {
  test(`${action}: unknown rights, metadata-only policy and absent permission are denied`, () => {
    assert.equal(permitsContent({ storage_policy: 'metadata_only', license_status: 'unknown' }, action, true), false);
    assert.equal(permitsContent({ storage_policy: 'full_text_allowed', license_status: 'unknown' }, action, true), false);
    assert.equal(permitsContent({ storage_policy: 'metadata_only', license_status: 'verified' }, action, true), false);
    assert.equal(permitsContent({ storage_policy: 'full_text_allowed', license_status: 'verified' }, action), false);
    assert.equal(permitsContent({ storage_policy: 'full_text_allowed', license_status: 'verified' }, action, true), true);
  });
}
