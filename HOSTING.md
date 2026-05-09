# Hosting The Graph

## Recommended path

Use a static host. The viewer is plain HTML plus CSV/JSON assets, so it does not need a backend.

Recommended order:

1. Netlify
2. GitHub Pages

Cloudflare Pages is a poor fit for the full bundle because the linked `results` corpus contains more than 20,000 files.

## Build the hosted bundle

From the workspace root:

```bash
python3 build_hosted_site.py
```

This writes `hosted_site/` with:

- `index.html` pointing at the category viewer
- graph CSV/JSON assets
- `results/` JSON files used by the node document links
- `.nojekyll`
- `_redirects`

If you only want the graph and do not care about the per-node document links:

```bash
python3 build_hosted_site.py --skip-results
```

## Netlify

Fastest option:

1. Build `hosted_site/`
2. Open Netlify Drop
3. Drag `hosted_site/` into the browser

If you want persistent deploys from git instead, point Netlify at this repo and set the publish directory to `hosted_site` after running the build.

## GitHub Pages

Suitable if you want the site versioned in a repo.

1. Build `hosted_site/`
2. Push `hosted_site/` to a repository
3. In GitHub Pages settings, publish from that folder or from a branch that contains it

## Notes

- The full hosted bundle is much larger than the graph app alone because it includes `results/`.
- Without `results/`, the viewer still works, but clicking node document links will not resolve.
- The larger PDF/image releases downloaded under `source_docs/` are not part of the hosted viewer unless you explicitly add them.
