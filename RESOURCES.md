# Downloaded Resources (Epstein Workspace)

## 1) epstein-docs (GitHub)
- URL: https://github.com/epstein-docs/epstein-docs.github.io
- Local path: /Users/quaydragon/Documents/epstein/epstein-docs
- What it contains: OCR/processed JSON corpus with extracted entities (`entities.people`, orgs, dates, etc.)
- Size in this workspace: ~240 MB
- File count: ~29,439 JSON documents under `results/`

## 2) markramm/EpsteinFiles (GitHub)
- URL: https://github.com/markramm/EpsteinFiles
- Local path: /Users/quaydragon/Documents/epstein/markramm-epsteinfiles
- What it contains: consolidated text corpus (`documents/`) and search tooling
- Size in this workspace: ~79 MB
- File count: ~2,895 text documents under `documents/`

## Notes
- Hugging Face dataset mirror `tonsenaut/EPSTEIN_FILES_20K` appears gated/private from this environment (API returns auth error), so it was not downloaded.
- Name network output generated from the `epstein-docs` JSON entity extraction is in:
  - `/Users/quaydragon/Documents/epstein/network_output/nodes.csv`
  - `/Users/quaydragon/Documents/epstein/network_output/edges.csv`
