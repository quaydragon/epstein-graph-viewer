# Epstein Graph Viewer

Static hosting bundle for the Epstein name-network viewer.

## Publish

The site is built into `hosted_site/`.

For GitHub Pages, publish the repository and configure Pages to serve from the branch root or the `hosted_site/` folder, depending on the repo layout you choose.

## Rebuild

```bash
python3 build_hosted_site.py
```

## Notes

- The hosted bundle includes the graph assets and linked `results/` JSON files.
- Large local download and OCR workspaces are intentionally not tracked in git.
