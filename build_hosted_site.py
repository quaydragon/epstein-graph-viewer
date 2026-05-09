#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path


SITE_FILES = [
    "network_view.html",
    "network_view_categories.html",
    "nodes.csv",
    "edges.csv",
    "person_categories.csv",
    "person_roles.csv",
    "person_documents.json",
    "person_summaries.json",
]


def copy_file(src: Path, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def parse_args():
    parser = argparse.ArgumentParser(description="Build a static hosting bundle for the Epstein graph viewer.")
    parser.add_argument(
        "--network-output",
        default="network_output",
        help="Directory containing the HTML viewer and graph data files.",
    )
    parser.add_argument(
        "--results-dir",
        default="epstein-docs/results",
        help="Directory containing JSON document files linked from the viewer.",
    )
    parser.add_argument(
        "--output-dir",
        default="hosted_site",
        help="Directory to write the static hosting bundle into.",
    )
    parser.add_argument(
        "--skip-results",
        action="store_true",
        help="Do not copy the linked JSON results corpus into the hosted bundle.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    network_output = Path(args.network_output)
    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)

    if not network_output.exists():
        raise SystemExit(f"network output directory not found: {network_output}")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for filename in SITE_FILES:
        src = network_output / filename
        if not src.exists():
            raise SystemExit(f"required file missing: {src}")
        copy_file(src, output_dir / filename)

    # Serve the category view as the homepage.
    copy_file(network_output / "network_view_categories.html", output_dir / "index.html")

    # Prevent GitHub Pages from invoking Jekyll processing.
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    # Netlify/GitHub Pages will otherwise 404 on "/" if index.html is absent.
    (output_dir / "_redirects").write_text("/ /index.html 200\n", encoding="utf-8")

    if not args.skip_results:
        if not results_dir.exists():
            raise SystemExit(f"results directory not found: {results_dir}")
        shutil.copytree(results_dir, output_dir / "results")

    total_files = sum(1 for p in output_dir.rglob("*") if p.is_file())
    total_bytes = sum(p.stat().st_size for p in output_dir.rglob("*") if p.is_file())

    print(f"Hosted site written to: {output_dir}")
    print(f"Files: {total_files}")
    print(f"Bytes: {total_bytes}")
    print(f"Includes results corpus: {'no' if args.skip_results else 'yes'}")


if __name__ == "__main__":
    main()
