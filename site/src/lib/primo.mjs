// Primo's Easy Chat passwords (Violet City Pokémon Center): the encoder, ported from
// work/tools/primo_passwords.py (encode()). Plain JS so Node can test it against the Python tool:
//   node work/tools/site/test_primo.mjs
// The password depends only on the 16-bit public Trainer ID and the reward (0-7 wallpaper, 8-10 Egg).

/** Rotate the big-endian bit string b[0..n-1] left by `count` bits (in place). */
function rotl(b, n, count) {
	const total = 8 * n;
	let r = ((total - (count % total)) % total); // as a right rotation, like the game's code
	for (; r > 0; r--) {
		const carry = b[n - 1] & 1;
		for (let j = n - 1; j > 0; j--) b[j] = ((b[j] >> 1) | ((b[j - 1] & 1) << 7)) & 0xff;
		b[0] = ((b[0] >> 1) | (carry << 7)) & 0xff;
	}
}

/**
 * Positions (0-based, in the password word list of length n) of the four words that make Primo
 * give `reward` to Trainer ID `tid`: phrase 1 = [0], [1]; phrase 2 = [2], [3].
 * @param {number} tid 0-65535
 * @param {number} reward 0-10
 * @param {number} n length of the password word list
 * @param {number} [marker=6]
 * @param {number} [rotateAll=5]
 * @returns {number[]}
 */
export function encodeIndices(tid, reward, n, marker = 6, rotateAll = 5) {
	if (!(reward >= 0 && reward <= 10)) throw new RangeError('reward must be 0-10');
	tid &= 0xffff;
	const hi = tid >> 8, lo = tid & 0xff;
	const b0 = ((marker << 4) | reward) & 0xff;
	const b = [b0, hi ^ b0, lo ^ b0, ((b0 + hi) * lo) & 0xff];
	rotl(b, 3, b[3] & 0x0f);
	const m = (b[3] & 0xf0) | (b[3] >> 4);
	for (let i = 0; i < 3; i++) b[i] ^= m;
	rotl(b, 4, rotateAll);
	const idx = [b[0]];
	for (let i = 1; i < 4; i++) idx.push((idx[i - 1] + b[i]) % n);
	return idx;
}
