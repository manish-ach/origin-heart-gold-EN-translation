# TypeScript review and existing-behavior hardening

No new editor features. Save-format rules and mutation behavior stay unchanged.

## Changes

- Expected failures are `EditorError` values with stable category codes and typed
  item context. Item-name messages use context rather than parsing error text.
  Unknown thrown values have a safe fallback and are never string-coerced. Read
  failures preserve their cause for diagnostics while displaying actionable text.
- A replacement save is read and fully validated before replacing active state.
  Invalid size/checksum/party records and file-read failures leave the existing
  save, applied changes and drafts intact. Stale asynchronous reads cannot replace
  a newer selection. Rendering failures roll back the session, and the picker is
  reset so selecting the same file can trigger another attempt.
- DOM lookups verify element constructors; move form fields have named types;
  six-stat records are constructed completely with explicit native ordering.
  Pocket IDs and Pokérus values are guarded unions. The bundled provider exposes
  its guaranteed catalogs. Binary bounds assertions remain where bounds have
  already been validated; they are not replaced with arbitrary defaults.
- Compiler checks additionally enforce exact optional properties, unused locals
  and parameters, complete returns and switch fallthrough prevention.
- Real type-aware ESLint runs on handwritten TypeScript. Rules cover floating and
  misused promises, thrown values, unknown rejection values, explicit `any`, type
  imports and core control-flow mistakes. The async DOM listener now explicitly
  starts an internally handled promise. Generated data is compiler/schema-tested
  rather than style-linted.

## Tooling and repeatable gates

```sh
npm --prefix work/save-editor run check
ORIGIN_EN_ROM=/path/to/existing/English.nds npm --prefix work/save-editor run check
```

`check` runs `typecheck`, `lint`, then `test` (including build). Without a local ROM,
only the optional exhaustive ROM-equivalence test is skipped. No game assets are
needed for the synthetic tests. No dependencies or ROMs were downloaded.

Pinned versions are TypeScript5.8.3, ESLint9.28.0, and
`@typescript-eslint/parser` / `eslint-plugin`8.34.0. These match the parser's peer
requirements; keeping the previous compiler5.9.3 would make that lint stack's clean
install incompatible. The existing installed compatible versions are linked only
inside ignored `node_modules/`; checked-in config contains no user-specific paths.
A fresh environment can install the declared dependencies with its normal package
manager workflow; a fresh network installation was not performed in this review.

## Regression coverage

Final gate (2026-10-04): strict compiler passed; ESLint passed with zero warnings;
**218 tests passed, zero failures and zero skips**, including local English-ROM
parity. Logs are in ignored `local/typescript-review-20261004/check.log`.

The ten new error/import tests cover typed errors and context, safe handling of
unknown thrown values, file-read causes, declared versus actual byte length,
checksums and party validation, native stat ordering and enum guards.

Five additional tests execute the **actual app event handlers** through a minimal
DOM adapter, using invented synthetic saves:

1. Apply money, enter an EV draft, reject invalid-size and invalid-checksum files:
   original session, applied money and draft remain. Discarding the draft restores
   export availability; importing a later valid save resets the old session.
2. Reject an asynchronous file read and preserve the same state.
3. Resolve an old pending read after a newer successful import: newer save wins.
4. Reject an old pending read after a newer successful import: success stays shown.
5. Inject a new-session render failure: applied edits/drafts roll back, and a later
   successful import still works. File-input reset permits same-file retries.

This adapter does not implement native browser validity, file-picker behavior or
file delivery. Live browser checks could not run in this turn: documented browser
discovery returned no browsers, and opening the preview was queued for the task
without making a browser available. The prior actual download/reopen/game evidence
is in `verification-export.md`; this review does not claim a fresh browser run.

Existing save, Pokémon cipher, mutation allowlist, stats, inventory, named choice,
trait, bundled-data and local-ROM parity tests remain part of the full gate.
