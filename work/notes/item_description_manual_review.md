# Item descriptions: pending manual review

Status: approved by the user on 2026-10-04 and applied as part of the 33-entry review. The exact approved revisions and pre-edit backups are recorded in `work/build/approved-review-20261004/application.json` and `before-banks/`. The candidate ROM and verification results are in that same directory. Description buffers and game logic were not changed. The earlier alternatives below are historical, not the applied text.

The full side-by-side Chinese/current English/proposed English review is stored
locally at `work/build/description-shortening/review.md`. Machine-readable
alternatives are in `reviewed_proposals.json` in that directory, and measured
lengths/layout/QA results are in `validation.json`. These files remain ignored
because the review includes local source text and US-seeded wording.

Affected bank: `a027/0218`; IDs 95, 97, 111, 218, 230, 231, 232, 233, 239, 245,
246, 288, 295, 314, 326, 352 and 389.

There are 17 capacity-only drafts, five separate source-fidelity alternatives,
and two unselected readings for ID 97. All 24 variants were checked against the
114-unit limit including the terminator, three lines of at most 215 pixels in
fonts 0 and 1, and the project QA rules. The checks reported zero errors and
warnings. Runtime rendering has not been tested for these proposed edits.

Review points:

- ID 97: the Chinese timing can describe longer ripening or a longer period
  remaining ripe. Select a reading or retain ambiguity before approving text.
- ID 218: the existing English omits increased friendship gain.
- ID 288: the existing English makes transfer uncertain and does not clearly
  specify an incoming contact attack.
- ID 295: the existing English omits guaranteed switching success.
- ID 314: the existing English introduces a smell characterization.
- ID 326: the existing English adds a hooked shape.

Recommended review order: approve the straightforward minimal drafts, consider
the five source-fidelity alternatives, and leave ID 97 unresolved until its
meaning is agreed. Wording changes can resolve the capacity issue without an
executable-code patch. Any approved application still needs an isolated candidate
build and runtime verification.

No translation bank, game code patch, graphics asset, ROM or decision register
was changed to create this proposal. Background and the alternative capacity
patch are documented in `tooling_findings.md` and
`item_description_fix_proposal.md`.
