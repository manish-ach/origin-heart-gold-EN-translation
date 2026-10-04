import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

test('browser entrypoint only imports bundled reference data; page asks only for save', async () => {
  const root = new URL('../', import.meta.url);
  const html = await readFile(new URL('index.html', root), 'utf8');
  assert.equal((html.match(/type="file"/g) ?? []).length, 1);
  assert.match(html, /English Origin HeartGold v4\.0\.3/);
  assert.doesNotMatch(html, /rom-input|accept="\.nds"/);
  const visited = new Set();
  async function visit(file) {
    if (visited.has(file)) return;
    visited.add(file);
    assert.notEqual(file, 'rom.js', 'developer ROM reader must not enter browser graph');
    const code = await readFile(new URL(`dist/${file}`, root), 'utf8');
    for (const match of code.matchAll(/(?:from\s*|import\s*)['"]\.\/([^'"]+)['"]/g)) await visit(match[1]);
  }
  await visit('app.js');
  assert.ok(visited.has('bundled-data.js'));
});
