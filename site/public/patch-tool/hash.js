// Incremental CRC32 and SHA-1 for large files, fed chunk by chunk (no 128 MB copies in memory).
// Used by the patcher worker and by work/tools/site/test_patcher.mjs.

const CRC_TABLE = (() => {
	const t = new Uint32Array(256);
	for (let n = 0; n < 256; n++) {
		let c = n;
		for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
		t[n] = c >>> 0;
	}
	return t;
})();

export class Crc32 {
	constructor() { this.crc = 0xffffffff; }
	update(bytes) {
		let c = this.crc;
		for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
		this.crc = c;
		return this;
	}
	/** Upper-case hex, 8 digits (C180A0E9). */
	hex() { return ((this.crc ^ 0xffffffff) >>> 0).toString(16).toUpperCase().padStart(8, '0'); }
}

export class Sha1 {
	constructor() {
		this.h = new Uint32Array([0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0]);
		this.w = new Uint32Array(80);
		this.block = new Uint8Array(64);
		this.blockLen = 0;
		this.length = 0; // bytes; Number is exact up to 2^53
	}
	compress(b, o) {
		const w = this.w;
		for (let i = 0; i < 16; i++, o += 4) w[i] = (b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3];
		for (let i = 16; i < 80; i++) {
			const x = w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16];
			w[i] = (x << 1) | (x >>> 31);
		}
		const h = this.h;
		let a = h[0], bb = h[1], c = h[2], d = h[3], e = h[4];
		for (let i = 0; i < 80; i++) {
			let f, k;
			if (i < 20) { f = (bb & c) | (~bb & d); k = 0x5a827999; }
			else if (i < 40) { f = bb ^ c ^ d; k = 0x6ed9eba1; }
			else if (i < 60) { f = (bb & c) | (bb & d) | (c & d); k = 0x8f1bbcdc; }
			else { f = bb ^ c ^ d; k = 0xca62c1d6; }
			const t = (((a << 5) | (a >>> 27)) + f + e + k + w[i]) | 0;
			e = d; d = c; c = (bb << 30) | (bb >>> 2); bb = a; a = t;
		}
		h[0] += a; h[1] += bb; h[2] += c; h[3] += d; h[4] += e;
	}
	update(bytes) {
		let i = 0;
		const n = bytes.length;
		this.length += n;
		if (this.blockLen) {
			while (i < n && this.blockLen < 64) this.block[this.blockLen++] = bytes[i++];
			if (this.blockLen < 64) return this;
			this.compress(this.block, 0);
			this.blockLen = 0;
		}
		for (; i + 64 <= n; i += 64) this.compress(bytes, i);
		while (i < n) this.block[this.blockLen++] = bytes[i++];
		return this;
	}
	/** Lower-case hex, 40 digits. Call once. */
	hex() {
		const bits = this.length * 8;
		const pad = new Uint8Array(((this.blockLen < 56 ? 56 : 120) - this.blockLen) + 8);
		pad[0] = 0x80;
		const hi = Math.floor(bits / 0x100000000), lo = bits >>> 0;
		const p = pad.length - 8;
		pad[p] = hi >>> 24; pad[p + 1] = hi >>> 16; pad[p + 2] = hi >>> 8; pad[p + 3] = hi;
		pad[p + 4] = lo >>> 24; pad[p + 5] = lo >>> 16; pad[p + 6] = lo >>> 8; pad[p + 7] = lo;
		const len = this.length;
		this.update(pad);
		this.length = len;
		return [...this.h].map((x) => x.toString(16).padStart(8, '0')).join('');
	}
}
