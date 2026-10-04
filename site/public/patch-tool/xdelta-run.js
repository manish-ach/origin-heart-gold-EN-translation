// Drives the xdelta3 WebAssembly build from kotcrab/xdelta-wasm (vendor/xdelta-wasm, Apache-2.0).
// The C side (native/xdelta3-wasm.c upstream) calls back into JS for every read and write, so the
// files are streamed in 4 MB blocks: the source ROM and the patch never sit in wasm memory whole.
// Shared by the browser worker (worker.js) and the Node check (work/tools/site/test_patcher.mjs).

export const BUFFER_SIZE = 4 * 1024 * 1024; // bytes per read/write block
export const CACHE_BLOCKS = 32; // source blocks kept in wasm memory (32 x 4 MB covers a 128 MB ROM)

/**
 * Apply a VCDIFF/xdelta3 patch (any secondary compression: LZMA, DJW, FGK).
 * @param {(arg: object) => Promise<any>} createModule  default export of vendor/xdelta-wasm/xdelta3.js
 * @param {object} io
 * @param {(offset: number, size: number) => Uint8Array} io.readSource  synchronous read of the original ROM
 * @param {(offset: number, size: number) => Uint8Array} io.readPatch   synchronous read of the patch
 * @param {(bytes: Uint8Array) => void} io.onOutput  receives a copy of each decoded block, in order
 * @param {(patchBytesRead: number) => void} [io.onProgress]
 * @param {Uint8Array|ArrayBuffer} [io.wasmBinary]  give the wasm bytes directly (Node); browsers fetch it
 * @returns {Promise<{ok: true} | {ok: false, code?: number, message: string}>}
 */
export async function applyPatch(createModule, io) {
	let module;
	let xdeltaMessage = '';
	const stderr = [];
	const copyIn = (bytes, ptr) => {
		module.HEAP8.set(bytes, ptr); // HEAP8 is replaced when memory grows: always read it from the module
		return bytes.length;
	};
	try {
		module = await createModule({
			...(io.wasmBinary ? { wasmBinary: io.wasmBinary } : {}),
			print: () => {},
			printErr: (line) => stderr.push(line),
		});
	} catch (e) {
		return { ok: false, message: 'Could not load the patcher (WebAssembly): ' + (e?.message || e) };
	}
	let patchPos = 0;
	module.readSource = (ptr, offset, size) => copyIn(io.readSource(Number(offset), size), ptr);
	module.readPatch = (ptr, offset, size) => {
		const n = copyIn(io.readPatch(Number(offset), size), ptr);
		patchPos = Number(offset) + n;
		io.onProgress?.(patchPos);
		return n;
	};
	module.outputFile = (ptr, size) => {
		io.onOutput(new Uint8Array(module.HEAP8.buffer, ptr, size).slice());
	};
	module.reportError = (ptr) => { xdeltaMessage = module.UTF8ToString(ptr); };
	try {
		const code = module.callMain([String(BUFFER_SIZE), String(CACHE_BLOCKS), 'false']);
		if (code !== 0) return { ok: false, code, message: xdeltaMessage || stderr.join('\n') || 'xdelta3 error ' + code };
		return { ok: true };
	} catch (e) {
		const text = String(e?.message || e);
		const oom = /memory|OOM|Cannot enlarge|abort/i.test(text + stderr.join(' '));
		return { ok: false, oom, message: oom ? 'The browser ran out of memory while patching.' : 'The patcher stopped: ' + text };
	}
}
