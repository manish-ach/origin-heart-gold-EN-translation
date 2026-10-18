# Moving the website to the host root (2026-10-18)

User decision 2026-10-18: the website moves from https://originheartgold.github.io/origin-heart-gold-EN-translation/
to https://originheartgold.github.io/. The user created the empty user-site repo
`originheartgold/originheartgold.github.io`, added a write deploy key to it and stored the private key as the Actions
secret `PAGES_DEPLOY_KEY` in `originheartgold/origin-heart-gold-EN-translation`.

## How it works

`.github/workflows/site.yml` (one commit, so it can be cherry-picked onto `main` together with
`work/tools/site/redirect_site.py` and its test):

1. **build** builds production with `GUIDE_SITE_URL=https://originheartgold.github.io`, `GUIDE_BASE=/`, and the
   tester preview (branch `PREVIEW_REF`, default `website-fix`) with `GUIDE_BASE=/preview/` (banner, noindex, no
   analytics). It adds `robots.txt` (allow all, `Disallow: /preview/`, `Sitemap:
   https://originheartgold.github.io/sitemap-index.xml`) and `.nojekyll`, then makes the redirect site for the old
   address with `redirect_site.py`. It uploads the root build (artifact `root-site`) and the redirect site (Pages
   artifact).
2. **deploy-root** (default branch of this repo only) force-pushes the root build as a single orphan commit by
   `github-actions[bot]` to `git@github.com:originheartgold/originheartgold.github.io.git`, branch `main`, with the
   deploy key (plain `ssh`, GitHub's ed25519 host key pinned). Then it waits up to 10 minutes for
   https://originheartgold.github.io/ to answer 200.
3. **deploy** (needs deploy-root) publishes the redirect site to this repo's GitHub Pages, i.e. the old address.
   If deploy-root failed, this job doesn't run and the old address keeps its previous deployment.

The redirect site: one stub per page (canonical to the new URL, `noindex`, meta refresh, `location.replace` keeping
query and `#anchor`, a visible link), a `404.html` that sends any other old path (including `/preview/...`) to the
same path at the root, and copies of every non-HTML file (patch `.xdelta` and `latest.json`, the PDF, the patch tool,
save editor files, licences, Team Builder JSON). Build internals (`_astro/`, `pagefind/`, sitemaps, robots.txt) are
left out.

Release, release-redeploy and preview-redeploy triggers are unchanged: they all end up in a run on the default branch.

## Checklist after merging to main

1. **Merge** the branch to `main` (or cherry-pick the site.yml commit and the URL/doc commit). The push starts the
   Website workflow. On this first run, `deploy-root` pushes to the new repo and then waits for the root to answer;
   it will most likely fail on the wait, because Pages isn't on yet. That is expected: the old address is not
   touched.
2. **Turn on Pages for the new repo:** `originheartgold/originheartgold.github.io` → Settings → Pages → Build and
   deployment → Source: **Deploy from a branch**, Branch: **main**, folder **/ (root)** → Save. Wait for the
   "pages build and deployment" run in that repo's Actions tab to finish (1–3 minutes).
3. **Check that "Enforce HTTPS"** is ticked on the new repo's Pages settings (it is the default for github.io).
4. **Rerun** the failed Website run in the main repo (Actions → Website → Re-run failed jobs), or start it with
   Actions → Website → Run workflow on `main`. This time deploy-root passes and `deploy` switches the old address to
   redirects.
5. **Verify** (private window):
   - https://originheartgold.github.io/ shows the home page; https://originheartgold.github.io/patch/ shows the
     patcher with the current release (not "isn't available").
   - https://originheartgold.github.io/robots.txt and https://originheartgold.github.io/sitemap-index.xml exist.
   - https://originheartgold.github.io/preview/ shows the tester preview with its banner.
   - Old links: https://originheartgold.github.io/origin-heart-gold-EN-translation/faq/#can-i-play-on-a-real-ds-dsi-or-3ds
     lands on the FAQ at the same anchor; .../origin-heart-gold-EN-translation/pokemon/cyndaquil/ lands on Cyndaquil;
     a made-up old path lands on the new 404 page at the same path; .../origin-heart-gold-EN-translation/preview/
     lands on the new preview.
   - An old download link still downloads: .../origin-heart-gold-EN-translation/patch/latest.json and the `.xdelta`
     it names, and .../origin-heart-gold-EN-translation/downloads/ PDF if the build made one.
   - The patcher at the new address patches a ROM end to end (the in-browser check is the same as before).
6. **Repo settings** (main repo → About, gear icon): Website `https://originheartgold.github.io/`.
7. **Search engines:** in Google Search Console and Bing Webmaster Tools, add `https://originheartgold.github.io/`
   (URL-prefix property), submit `https://originheartgold.github.io/sitemap-index.xml`, and in Google use the Change of
   Address tool only if it offers it for this property type (it needs domain-level properties, so probably not:
   the canonical links and redirects do the job instead).
8. **Analytics:** GoatCounter keeps counting (same origin), but paths lose the `/origin-heart-gold-EN-translation`
   prefix from now on; old and new paths show as separate rows.
9. **Announce** the new address on Discord/Reddit; the next release's notes and README.txt carry it (RELEASING.md).

## Rollback

- Quick: revert the site.yml commit on `main` and run the Website workflow. The old address gets the full site again
  (built for the project base), replacing the redirects.
- The root site can stay as it is or be switched off: new repo → Settings → Pages → Source: None. Don't delete the
  repo: its deploy key and the `PAGES_DEPLOY_KEY` secret are what the move needs if it is tried again.
- If only the push fails (e.g. the deploy key was revoked): nothing changes for players; the old address keeps the
  last deployment it had. Check the deploy key (new repo → Settings → Deploy keys, "Allow write access") and that the
  secret holds the matching private key.

## What could not be tested before the merge

- The real push to the new repo (deploy key, branch protection, Pages build from the branch).
- That GitHub Pages serves the project site's `404.html` for unknown paths under the old address while the user site
  owns the host root. GitHub documents that a project site's path takes precedence; the stubs and 404 mapping were
  tested locally with a server that behaves the same way.
