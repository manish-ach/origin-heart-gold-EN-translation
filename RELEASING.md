# Releasing

How a version (release candidate or final) goes out. Everything is done from the **developer account**
(`originheartgold`): git over the `github-originheartgold` SSH alias, and the GitHub **web UI** for the release page.
Do not use the `gh` CLI: it is logged in with a personal account.

The patch can't be built in CI (it needs the USA and Chinese ROMs, which never leave your machine), so a release is
half local, half CI. ROMs, saves and build inputs are never uploaded: only the xdelta, README and metadata.

## 1. Prepare (local)

1. Set the notice version: `Current version: 4.0.3-RC<N>` in `work/translate/banks/a027/0816.json`, string 4
   (see [CONTRIBUTING.md](CONTRIBUTING.md#release-notice-version)). It is embedded in the ROM; the release tag does not change it.
2. Add a `## [<version>] - <date>` section to `CHANGELOG.md` (e.g. `## [1.0.0-rc8] - 2026-10-20`). It becomes the release notes; `release.yml` adds a closing line with the website and patch page links.
3. Build the release patch and run its gates. The patch is one xdelta with three layers, each installed on the one
   before: the standard build, the difficulty settings, and the advanced trainer AI, which stays OFF until the player
   turns it on (D-2506). Run from the repository root, in this order:

   ```sh
   TAG=v1.0.0-rc9
   D=work/build/difficulty-v2/integration-impl
   OUT=work/build/release-ai/$TAG
   ROM=$OUT/origin_hg_v4.0.3_en_ai.nds
   P=work/advanced-ai/payload/payload.json
   # a. the standard build: work/build/origin_hg_v4.0.3_en_wip.nds
   .venv/bin/python work/tools/build.py
   # b. difficulty in release mode (the pinned tools, never DIFFICULTY_DEV_TOOLS=1), its independent
   #    verification, and its host and native checks
   .venv/bin/python work/research/difficulty-armips/build.py --enable-difficulty --input work/build/origin_hg_v4.0.3_en_wip.nds
   .venv/bin/python work/research/difficulty-armips/verify.py --receipt $D/receipt.json --out work/build/difficulty-v2/verify-$TAG
   .venv/bin/python work/research/difficulty-armips/tests/run.py --native        # as for rc8: VALIDATION.txt
   # c. the AI on difficulty's candidate, the xdelta and release.json
   .venv/bin/python work/advanced-ai/builder/release.py --tag $TAG --difficulty-receipt $D/receipt.json \
       --difficulty-verification work/build/difficulty-v2/verify-$TAG/verification.json --out-dir $OUT
   # d. the standard gates and the AI's three test levels, on the release ROM
   .venv/bin/python work/tools/check.py --full --strict-release --ai-rom "$ROM"   # gates + the AI's static level
   .venv/bin/python work/advanced-ai/testbench/run.py quick --rom "$ROM" --payload $P --workers 3 \
       --options-receipt $D/receipt.json                                         # about 20 min
   .venv/bin/python work/advanced-ai/testbench/run.py deep --rom "$ROM" --payload $P --workers 3   # 35-80 min
   ```

   - **Difficulty's input pin.** Difficulty's installer accepts one standard build, pinned by its SHA-256 (`INPUT_SHA`
     in `work/research/difficulty-armips/install.py`). If the standard build changed since the pin, re-pin difficulty
     and review the change first, as in `work/notes/main_difficulty_compatibility_20261013.md`.
   - **`release.py`** ([work/advanced-ai/builder/README.md](work/advanced-ai/builder/README.md)) refuses a
     development difficulty build, difficulty tools that differ from their release pins, a missing verification, an
     xdelta3 other than 3.2.0, and an AI payload, trainer-mark list or builder that differs from the commit. It
     writes into `$OUT`: the AI ROM (never distributed), its install receipt, `Origin_HeartGold_v4.0.3_EN_$TAG.xdelta`
     (made as `build.py` makes the standard patch, then re-applied to the USA ROM and compared with the AI ROM) and
     `release.json`. `release.json` chains the hashes of the standard build, difficulty's receipt, verification and
     candidate, the AI payload and its commit, the AI ROM and the xdelta. `--allow-development` is only for trials:
     the patch is then named `...-development.xdelta` and `release.json` says `"releasable": false`. Ship only a
     patch whose `release.json` says `"releasable": true`.
   - **The three levels.** All three must pass on `$ROM`; a SKIP does not count as a pass. `check.py` runs the
     standard gates on its own build of the same commit (in `work/build/check/`) and the AI's `ai-unit` and
     `ai-static` steps on `$ROM`. The quick level also checks the TRAINER AI row through difficulty's
     receipt. The deep level passes when its 80 AI-vs-AI logs equal
     `work/advanced-ai/testbench/references/en/aivsai.json` (compared only with the reference saves). Otherwise it
     passes only when the advanced AI wins 80–94% of the counted games; if the logs differ from the reference, the
     release notes name the change that moved them ([work/advanced-ai/docs/checks.md](work/advanced-ai/docs/checks.md)).
     Each level's result is in `work/build/advanced-ai/runs/tiers/<level>_en_<time>/summary.txt`.
4. Package into `work/release/<tag>/` (gitignored): copy only the `.xdelta` from `$OUT` (never the AI ROM or the
   receipts), then add `README.txt` and, optionally, `VALIDATION.txt`, the ZIP and `SHA256SUMS.txt`. Start
   `README.txt` from the previous release's, and update it for the AI:
   - the three lines that `release.py` prints (also `readme_lines` in `release.json`): `Patch:` with its `SHA-1`, and
     `Result ROM SHA-1:`, the AI ROM's SHA-1, which the website patcher checks its output against;
   - under STATUS: the optional advanced trainer AI, OFF by default, turned on with TRAINER AI (OFF / KEY / ALL) on
     Options page 2/2; that it has not been tested on real hardware, with a request to report how it runs on a DS,
     DSi or 3DS;
   - under CREDITS: `Advanced trainer AI: from the Spanish translation by luisvent.`
   - near the top: `Official website: https://originheartgold.github.io/` and
     `Patch in your browser: https://originheartgold.github.io/patch/` (older README.txt files still name the old
     address, originheartgold.github.io/origin-heart-gold-EN-translation/: replace it).

   `VALIDATION.txt`, as for rc8: the result line of each AI level's `summary.txt` and the hashes in `release.json`.
5. Write `latest.json` for the website's in-browser patcher: `python3 work/tools/site/patch_manifest.py <tag>`. It
   reads the xdelta and the `Result ROM SHA-1:` line of `README.txt`; nothing in it is specific to the AI.
6. Commit the version bump and CHANGELOG, and merge to `main`.

## 2. Tag (triggers CI)

```
git tag v1.0.0-rc8        # on the commit you built from
git push origin v1.0.0-rc8
```

`.github/workflows/release.yml` then:
- fails if `CHANGELOG.md` has no matching `## [<version>]` section, or (for `-rcN` tags) if `a027/0816.json` doesn't say `Current version: 4.0.3-RC<N>`;
- creates a **draft** release titled `<version>` with the CHANGELOG section as its notes (nothing happens if the release already exists).

Check the run under *Actions → Release*. If it failed, fix the file, then move the tag
(`git tag -f v1.0.0-rc8 && git push -f origin v1.0.0-rc8`) and the workflow reruns.

## 3. Upload and publish (web UI)

1. *Releases* → open the draft → **Edit**.
2. Drag in from `work/release/<tag>/`: the `.xdelta`, `README.txt`, **`latest.json`** (without it the website patcher stays off), and the ZIP if you made one.
3. Check the notes, tick **Set as the latest release** (or *pre-release* if you want it kept out of "Latest"; rc7 was a normal release).
4. **Publish release.**

Publishing triggers `site.yml` (`release: published`), which downloads `latest.json` and the xdelta, verifies the SHA-1 and redeploys https://originheartgold.github.io/patch/.
Check that run, then open the patch page and try it.

The website's [changelog page](https://originheartgold.github.io/changelog/), home release line and patch-page version come from `site/src/data/releases.json` and `site/src/data/contributors.json`: add the release there (a short player-facing summary written from `CHANGELOG.md`, and the contributors' names) and commit it with the release. `site/tests/changelog.test.mjs` fails the website build until every version in `CHANGELOG.md` is listed.

## 4. After

- Confirm the downloaded xdelta applied to a clean USA ROM gives the `Result ROM SHA-1` in the README.
- Announce (Discord / Reddit thread) with the CHANGELOG section.
