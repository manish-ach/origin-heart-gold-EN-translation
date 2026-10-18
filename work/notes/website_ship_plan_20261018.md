# Shipping the website branch (2026-10-18)

Nothing below has been pushed. The user runs these steps.

## State

- `website-fix-proposal` holds everything: the website fixes and audit work, the root-site move
  (`root_site_move.md`), `fix/site-export-built-rom` (merge `3103c164`: site data and player docs from the v1.0.0-rc8
  release ROM) and `origin/main` (merge `94a8e39c`: preview workflow, CI fix, check_save_harness test listing).
- The tested tree is `94a8e39c`. The tip is the commit that adds this note (documentation only; nothing it changes
  is built or tested). Check it with `git rev-parse website-fix-proposal`.
- `origin/main` (`d229cf98`), `origin/website-fix` (`744da168`) and the local `website-fix` (`d7e34ca4`, one commit
  ahead of origin) are all ancestors of the tip, so **each of the three pushes is a fast-forward**. There is no
  `origin/website-fix-proposal` yet.
- `develop` is not part of this. Merging the site export into `develop` later follows
  `site_export_built_rom_review.md` (M-1).

## Push

One atomic push, from any checkout of the repo:

```sh
git push --atomic origin website-fix-proposal:main website-fix-proposal:website-fix website-fix-proposal
```

Atomic keeps the three refs in step: the push to `main` starts the Website workflow (build, deploy-root, deploy),
and the push to `website-fix` starts `preview-redeploy`, which dispatches another run on `main`. Both runs see the
new `main`; the newer one cancels the older (shared `production` concurrency group), so one run deploys.
`website-fix-proposal` is not a workflow branch: pushing it starts nothing.

Afterwards, bring the local branches along (fast-forward only):
`git -C ~/Developer/poke-website-fix merge --ff-only website-fix-proposal` for `website-fix`. The main checkout
`~/Developer/poke` has uncommitted site changes on `main`; fast-forward it there (`git merge --ff-only origin/main`)
only after those are committed or set aside.

## PREVIEW_REF

Leave the repository variable `PREVIEW_REF` unset, or set it to `website-fix`. The workflow's push trigger lists
`website-fix` by name, so a different value would build that branch on production runs but pushes to it would not
redeploy the preview. Right after the push, `/preview/` shows the same content as production (same commit) until
`website-fix` moves on.

## After the push

Follow the checklist in `work/notes/root_site_move.md` ("Checklist after merging to main"), in short:

1. The first Website run on `main` most likely fails in deploy-root's "Wait until the root site answers": Pages is
   not on yet for `originheartgold/originheartgold.github.io`. Expected; the old address is untouched.
2. Turn on Pages for the user-site repo (Deploy from a branch, `main`, `/ (root)`), wait for its build, check that
   Enforce HTTPS is ticked.
3. Re-run the failed jobs of the Website run (or Run workflow on `main`). deploy-root passes, then `deploy` turns the
   old address into the redirect site.
4. Verify in a private window: home, /patch/ with the current release, robots.txt, sitemap-index.xml, /preview/
   with its banner, old links with anchors, an old made-up path, old download links (`patch/latest.json`, its
   `.xdelta`, the PDF), and one end-to-end patch.
5. Repo About → Website: `https://originheartgold.github.io/`.
6. Search Console and Bing: add the new URL-prefix property, put the HTML-tag values in the Actions variables
   `GUIDE_GOOGLE_VERIFICATION` and `GUIDE_BING_VERIFICATION`, re-run the workflow, verify, submit the sitemap.
7. Announce the new address (Discord, Reddit); the next release's notes and README.txt carry it.

Rollback: `root_site_move.md` → Rollback.
