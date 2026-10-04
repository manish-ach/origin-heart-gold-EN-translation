#!/usr/bin/env node
// Check the website's in-browser patcher (site/public/patch-tool + the vendored xdelta-wasm build) in Node,
// on real local files. Nothing is written to disk: the patched ROM is hashed as it streams out.
//
//   node work/tools/site/test_patcher.mjs                       # newest work/release/<tag>/ patch
//   node work/tools/site/test_patcher.mjs --patch X.xdelta --expect <sha1> [--rom base.nds] [--xdelta3]
//   node work/tools/site/test_patcher.mjs --zip a.zip [b.zip …]  # only unzip + hash, like the page does for a .zip
//
// It checks: the base ROM's CRC32/SHA-1 (JS hash code against Node's crypto), that the wasm build
// decodes the LZMA-secondary patch, and that the output SHA-1 equals the release README's
// "Result ROM SHA-1" (and, with --xdelta3, the output of the native `xdelta3 -d`).
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const PUB = path.join(REPO, 'site/public');
const { applyPatch } = await import(pathToFileURL(path.join(PUB, 'patch-tool/xdelta-run.js')));
const { Crc32, Sha1 } = await import(pathToFileURL(path.join(PUB, 'patch-tool/hash.js')));
const createModule = (await import(pathToFileURL(path.join(PUB, 'vendor/xdelta-wasm/xdelta3.js')))).default;

const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };
const US_CRC = 'C180A0E9';
const US_SHA1 = '4fcded0e2713dc03929845de631d0932ea2b5a37';

// --zip: open each archive with patch-tool/zip.js (the worker's code) and check the .nds it picks.
if (args.includes('--zip')) {
	const { isZip, listZip, ndsEntries, readEntry } = await import(pathToFileURL(path.join(PUB, 'patch-tool/zip.js')));
	let bad = false;
	for (const f of args.slice(args.indexOf('--zip') + 1)) {
		const blob = await fs.openAsBlob(f);
		try {
			if (!(await isZip(blob))) throw new Error('not a zip');
			const nds = ndsEntries(await listZip(blob));
			if (!nds.length) throw new Error('no .nds inside');
			const entry = nds.find((e) => e.crc32 === US_CRC) || nds.reduce((a, b) => (b.size > a.size ? b : a));
			const crc = new Crc32(), sha = new Sha1();
			let n = 0;
			const t0 = Date.now();
			await readEntry(blob, entry, (c) => { crc.update(c); sha.update(c); n += c.length; });
			const ok = crc.hex() === US_CRC && sha.hex() === US_SHA1 && n === 134217728;
			console.log(`${ok ? 'OK  ' : 'FAIL'} ${path.basename(f)}: ${entry.name} (method ${entry.method}, ${nds.length} .nds) ${n} bytes CRC32 ${crc.hex()} in ${Date.now() - t0} ms`);
			if (!ok) bad = true;
		} catch (e) {
			console.log(`ERR  ${path.basename(f)}: ${e.message}`);
			bad = true;
		}
	}
	process.exit(bad ? 1 : 0);
}

function newestRelease() {
	const dir = path.join(REPO, 'work/release');
	const found = [];
	for (const tag of fs.readdirSync(dir)) {
		if (tag === 'wip') continue;
		const d = path.join(dir, tag);
		if (!fs.statSync(d).isDirectory()) continue;
		for (const f of fs.readdirSync(d)) {
			if (f.endsWith('.xdelta')) found.push({ tag, patch: path.join(d, f), readme: path.join(d, 'README.txt'), mtime: fs.statSync(path.join(d, f)).mtimeMs });
		}
	}
	found.sort((a, b) => b.mtime - a.mtime);
	return found[0];
}

const rel = opt('--patch') ? { patch: path.resolve(opt('--patch')), tag: '(given)' } : newestRelease();
if (!rel) { console.error('No work/release/<tag>/*.xdelta found'); process.exit(2); }
let expect = opt('--expect');
if (!expect && rel.readme && fs.existsSync(rel.readme)) {
	expect = fs.readFileSync(rel.readme, 'utf8').match(/Result ROM SHA-1:\s*([0-9a-fA-F]{40})/)?.[1]?.toLowerCase();
}
const rom = path.resolve(opt('--rom') || path.join(REPO, 'work/rom/Pokemon - HeartGold Version (USA).nds'));
console.log(`release ${rel.tag}: ${path.relative(REPO, rel.patch)}`);
console.log(`expected output SHA-1: ${expect || '(unknown)'}`);

// 1. Base ROM hashes: our JS code against Node's crypto.
const romFd = fs.openSync(rom, 'r');
const romSize = fs.fstatSync(romFd).size;
const readAt = (fd, total) => (offset, size) => {
	const n = Math.max(0, Math.min(size, total - offset));
	const buf = Buffer.alloc(n);
	if (n) fs.readSync(fd, buf, 0, n, offset);
	return new Uint8Array(buf.buffer, buf.byteOffset, n);
};
const readRom = readAt(romFd, romSize);
let t = Date.now();
const crc = new Crc32(), sha = new Sha1(), ref = createHash('sha1');
for (let off = 0; off < romSize; off += 8 << 20) { const b = readRom(off, 8 << 20); crc.update(b); sha.update(b); ref.update(b); }
const romSha = sha.hex(), refSha = ref.digest('hex');
console.log(`base ROM: ${romSize} bytes, CRC32 ${crc.hex()}, SHA-1 ${romSha} (node crypto ${refSha}) in ${Date.now() - t} ms`);
let failed = false;
if (romSha !== refSha) { console.error('FAIL: JS SHA-1 differs from node crypto'); failed = true; }
if (crc.hex() !== US_CRC || romSha !== US_SHA1) { console.error('FAIL: base ROM is not HeartGold (USA) C180A0E9'); failed = true; }

// 2. Apply the patch with the wasm build, hashing the output as it streams.
const patchFd = fs.openSync(rel.patch, 'r');
const patchSize = fs.fstatSync(patchFd).size;
const outSha = new Sha1(), outRef = createHash('sha1');
let outSize = 0, lastPct = -1;
t = Date.now();
const res = await applyPatch(createModule, {
	wasmBinary: fs.readFileSync(path.join(PUB, 'vendor/xdelta-wasm/xdelta3.wasm')),
	readSource: readRom,
	readPatch: readAt(patchFd, patchSize),
	onOutput: (b) => { outSha.update(b); outRef.update(b); outSize += b.length; },
	onProgress: (pos) => { const p = Math.floor((pos / patchSize) * 10) * 10; if (p !== lastPct) { lastPct = p; process.stdout.write(`  ${p}%`); } },
});
process.stdout.write('\n');
const wasmSha = outSha.hex(), wasmRef = outRef.digest('hex');
const mem = process.memoryUsage();
console.log(`wasm patch: ${res.ok ? 'ok' : 'FAILED ' + res.message} in ${Date.now() - t} ms; output ${outSize} bytes, SHA-1 ${wasmSha} (node crypto ${wasmRef}); rss ${(mem.rss / 1048576).toFixed(0)} MB`);
if (!res.ok || wasmSha !== wasmRef) failed = true;
if (expect && wasmSha !== expect) { console.error(`FAIL: output SHA-1 ${wasmSha} != expected ${expect}`); failed = true; }
if (expect && wasmSha === expect) console.log('output SHA-1 matches the release README');

// 3. Optional: native xdelta3, streamed to a hash (no file written).
if (args.includes('--xdelta3')) {
	const h = createHash('sha1');
	const code = await new Promise((resolve) => {
		const p = spawn('xdelta3', ['-d', '-c', '-s', rom, rel.patch], { stdio: ['ignore', 'pipe', 'inherit'] });
		p.stdout.on('data', (d) => h.update(d));
		p.on('error', () => resolve(-1));
		p.on('close', resolve);
	});
	const nat = h.digest('hex');
	console.log(`native xdelta3 -d: exit ${code}, SHA-1 ${nat}`);
	if (code !== 0 || nat !== wasmSha) { console.error('FAIL: native xdelta3 output differs'); failed = true; }
}
console.log(failed ? 'RESULT: FAIL' : 'RESULT: OK');
process.exit(failed ? 1 : 0);
