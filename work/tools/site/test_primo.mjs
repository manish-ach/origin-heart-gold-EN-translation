#!/usr/bin/env node
// Check the website's Primo password encoder (site/src/lib/primo.mjs) against the Python tool
// (work/tools/primo_passwords.py, encode()), for every Trainer ID 0-65535 and every reward 0-10.
// Also checks site/src/data/primo.json (word count, picker positions, no Chinese).
//
//   node work/tools/site/test_primo.mjs
//
// Needs no ROM: both sides run on word-list positions 0..N-1, N = the number of words in primo.json.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const { encodeIndices } = await import(pathToFileURL(path.join(REPO, 'site/src/lib/primo.mjs')));
const data = JSON.parse(fs.readFileSync(path.join(REPO, 'site/src/data/primo.json'), 'utf8'));
const N = data.words.length;

let problems = 0;
const fail = (msg) => { problems++; if (problems <= 20) console.log('  ' + msg); };

// data file
const cjk = /[　-鿿＀-￯]/;
for (const w of data.words) {
	if (!w.en || cjk.test(w.en) || !w.category || cjk.test(w.category) || !(w.position >= 1)) fail('bad word ' + JSON.stringify(w));
}
for (const r of data.rewards) if (!r.en || cjk.test(r.en)) fail('bad reward ' + JSON.stringify(r));
const values = data.rewards.map((r) => r.value).sort((a, b) => a - b).join(',');
if (values !== '0,1,2,3,4,5,6,7,8,9,10') fail('rewards are not 0-10: ' + values);

// Python reference: 65536 x 11 x 4 positions as little-endian u16
const py = `
import sys
sys.path.insert(0, ${JSON.stringify(path.join(REPO, 'work/tools'))})
from primo_passwords import encode
from array import array
wl = list(range(${N}))
out = array('H')
for tid in range(65536):
    for r in range(11):
        out.extend(encode(tid, r, wl))
if sys.byteorder != 'little':
    out.byteswap()
sys.stdout.buffer.write(out.tobytes())
`;
const t0 = Date.now();
const buf = execFileSync('python3', ['-c', py], { maxBuffer: 64 << 20 });
const ref = new Uint16Array(buf.buffer, buf.byteOffset, buf.byteLength / 2);
if (ref.length !== 65536 * 11 * 4) fail(`Python gave ${ref.length} values`);
let k = 0, mismatches = 0;
for (let tid = 0; tid < 65536; tid++) {
	for (let r = 0; r < 11; r++) {
		const js = encodeIndices(tid, r, N, data.marker, data.rotate_all_bits);
		for (let i = 0; i < 4; i++, k++) {
			if (js[i] !== ref[k]) {
				mismatches++;
				fail(`tid ${tid} reward ${r}: JS ${js} vs Python ${[...ref.slice(k - i, k - i + 4)]}`);
				k += 3 - i;
				break;
			}
		}
	}
}
console.log(`primo: ${65536 * 11} passwords compared (N=${N}), ${mismatches} mismatches, ${problems - mismatches} data problems, ${((Date.now() - t0) / 1000).toFixed(1)} s`);
process.exit(problems ? 1 : 0);
