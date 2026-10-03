const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app/static/js/theme.js'), 'utf8');
for (const preference of ['light', 'dark', 'system']) {
    for (const systemDark of [true, false]) {
        test(`${preference} with system dark=${systemDark}`, () => {
            let listener;
            const root = {dataset: {themePreference: preference}, style: {}};
            const media = {matches: systemDark, addEventListener: (_, fn) => listener = fn};
            const meta = {};
            vm.runInNewContext(source, {
                document: {documentElement: root, querySelector: selector => selector.startsWith('meta') ? meta : null},
                window: {matchMedia: () => media},
                localStorage: {getItem: () => null, setItem: () => {}},
            });
            const expected = preference === 'dark' || (preference === 'system' && systemDark);
            assert.equal(root.dataset.theme, expected ? 'dark' : 'light');
            assert.equal(root.style.colorScheme, root.dataset.theme);
            media.matches = !systemDark;
            listener();
            const updated = preference === 'dark' || (preference === 'system' && !systemDark);
            assert.equal(root.dataset.theme, updated ? 'dark' : 'light');
            assert.equal(meta.content, updated ? '#101c28' : '#0f766e');
        });
    }
}
