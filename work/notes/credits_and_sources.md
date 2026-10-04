# Credits and sources

**Status (reviewed 2026-09-29): current.**

- **起源心金 (Origin HeartGold)**: original hack by 雁南飞TB (Bilibili space 1461403176). v3 "complete edition" shipped in three protagonist skins (Anime / Origins / Special).
- **v4.0.x**: developed by Alex (not 雁南飞TB), built on hg-engine. Profile with release history: https://youhua.baidu.com/home/main?lp=home_follow_main&un=chendelpiero
- **Chinese patches (v3 Anime/Origins/Special, v4.0.3) and docs**: packaged by u/riap0526.
- **Partial v3 English (Origins/Red skin)**: u/Shake69, made with DS Pokémon ROM Editor (DSPRE) around early 2025. By their account it fully translates moves, items, menus and the Pokédex, and the story up to about Cerulean. Used here as translation memory.
- **Base ROM for all patches**: Pokémon HeartGold (USA) `IPKE`, CRC32 C180A0E9, MD5 258cea3a62ac0d6eb04b5a0fd764d788. Verified: v4.0.3 Cn and v3 Eng apply cleanly. The patched hack ROM itself identifies as `IPKJ` and keeps the Japanese code layout (120 overlays, against 129 in the USA ROM); see `hardcoded_text.md`.
- Source thread: r/PokemonROMhacks, "The best Pokémon DS ROM hack is Chinese (and almost nobody knows about it)", 2026-09-28 (saved copy at `reddit-thread-1wsbpj6.md` in the repo root, local only: `.gitignore` keeps it out of git).

## Website patcher (site/ → /patch/)

- **xdelta-wasm** by Kotcrab: https://github.com/kotcrab/xdelta-wasm, commit `007c6b45ef10ac4121aff3dfa445ab47c78c60cd` (2026-03-28), Apache License 2.0 (redistribution allowed with the licence text; no NOTICE file upstream). We vendor its built `xdelta3.js` and `xdelta3.wasm` unmodified in `site/public/vendor/xdelta-wasm/` (with `LICENSE.txt` and `SOURCE.txt`, which holds the sha256 of both), fetched 2026-10-04 from the deployed site https://kotcrab.github.io/xdelta-wasm/, which that repository's workflow builds from the commit above. Our own worker and wrapper (`site/public/patch-tool/`) are modelled on its `public/xdelta3.worker.js`.
- **xdelta3** by Joshua MacDonald: https://github.com/jmacd/xdelta (xdelta-wasm submodule commit `0525275fe4b553a10f38e455d30c60dc6ed9b45d`), Apache License 2.0. Built with secondary compression DJW, FGK and **LZMA**, so it decodes our `xdelta3 -e -9 -S lzma` patches (checked with `node work/tools/site/test_patcher.mjs`).
- **liblzma** from XZ Utils 5.4.6 (linked into the wasm): public domain.
- Credited on the site's About page (Credits) and on /patch/.

## Release notes to remember
- Ship an xdelta patch against the USA ROM only; never a full ROM (subreddit rule 1).
- Credit 雁南飞TB, Alex, u/Shake69 (TM source) and u/riap0526. u/Shake69 granted permission to reuse their v3 English work (confirmed by the user, 2026-09-28). The project distributes only xdelta patches, never the hack or a ROM.

## Contacting the creators

The hack's own intro notice (a027/0816) says: remade with 雁南飞TB's authorisation, a fan work, no commercial use (禁止用于营利行为), free from the Tieba or QQ group, and "credit the source when reposting" (转载请声明出处).

- **Alex (v4.0.x author):** QQ group 1055021987 (the official channel in the intro notice) and Baidu Tieba 起源心金吧 (https://tieba.baidu.com/f?kw=起源心金). No direct contact known.
- **雁南飞TB (original author):** Bilibili space 1461403176 (https://space.bilibili.com/1461403176). Send a private message (私信) or comment on the "完结版" video https://www.bilibili.com/video/BV1pp421R78c/.
- Credits: Alex and 雁南飞TB are credited as the hack's authors in the README, the site's About page and the release notes. u/Shake69 gave permission to reuse the v3 English (2026-09-28). The project distributes only xdelta patches.
