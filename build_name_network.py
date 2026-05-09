#!/usr/bin/env python3
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path


NAME_NOISE = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "jr",
    "sr",
    "ii",
    "iii",
    "iv",
}


def is_redacted_placeholder(name: str) -> bool:
    n = name.lower()
    if "[redacted]" in n or "redacted" in n:
        return True
    if "jane doe" in n or "john doe" in n:
        return True
    if "victim" in n or re.search(r"\bdoe\b", n):
        return True
    return False


def normalize_name(name: str) -> str:
    raw = re.sub(r"\s+", " ", name.strip())
    if not raw:
        return ""

    if is_redacted_placeholder(raw):
        placeholder = raw.replace("[", "").replace("]", "")
        placeholder = re.sub(r"\s+", " ", placeholder).strip(" \t-_,;:")
        return placeholder.title() if placeholder else ""

    name = raw
    name = re.sub(r"^[\W_]+|[\W_]+$", "", name)
    parts = [p for p in re.split(r"\s+", name) if p]
    cleaned = []
    for part in parts:
        p = re.sub(r"[^A-Za-z\-']", "", part)
        if not p:
            continue
        if p.lower().rstrip(".") in NAME_NOISE:
            continue
        cleaned.append(p)

    if len(cleaned) < 2:
        return ""

    normalized = " ".join(cleaned)
    normalized = normalized.title()
    return normalized


def load_people_from_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    people = data.get("entities", {}).get("people", [])
    if not isinstance(people, list):
        return []

    normalized = []
    seen = set()
    for person in people:
        if not isinstance(person, str):
            continue
        n = normalize_name(person)
        if not n:
            continue
        if n in seen:
            continue
        seen.add(n)
        normalized.append(n)

    return normalized


def build_network(results_dir: Path):
    node_doc_freq = Counter()
    edge_doc_freq = Counter()
    docs_processed = 0

    json_files = list(results_dir.rglob("*.json"))
    for file_path in json_files:
        names = load_people_from_json(file_path)
        if not names:
            continue

        docs_processed += 1

        for n in names:
            node_doc_freq[n] += 1

        for a, b in combinations(sorted(names), 2):
            edge_doc_freq[(a, b)] += 1

    return docs_processed, len(json_files), node_doc_freq, edge_doc_freq


def write_nodes_csv(path: Path, node_doc_freq: Counter):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label", "document_frequency"])
        for name, freq in node_doc_freq.most_common():
            writer.writerow([name, name, freq])


def write_edges_csv(path: Path, edge_doc_freq: Counter, min_weight: int):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "target", "weight"])
        for (a, b), w in edge_doc_freq.most_common():
            if w < min_weight:
                continue
            writer.writerow([a, b, w])


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a person-name co-occurrence network from epstein-docs JSON results."
    )
    parser.add_argument(
        "--results-dir",
        default="epstein-docs/results",
        help="Path to directory containing JSON result files (default: epstein-docs/results)",
    )
    parser.add_argument(
        "--output-dir",
        default="network_output",
        help="Output directory for nodes.csv and edges.csv (default: network_output)",
    )
    parser.add_argument(
        "--min-edge-weight",
        type=int,
        default=1,
        help="Minimum co-occurrence count required to keep an edge (default: 1)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)

    if not results_dir.exists():
        raise SystemExit(f"Results directory does not exist: {results_dir}")

    docs_processed, total_json, node_doc_freq, edge_doc_freq = build_network(results_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = output_dir / "nodes.csv"
    edges_path = output_dir / "edges.csv"

    write_nodes_csv(nodes_path, node_doc_freq)
    write_edges_csv(edges_path, edge_doc_freq, args.min_edge_weight)

    edge_count_after_filter = sum(1 for _, w in edge_doc_freq.items() if w >= args.min_edge_weight)

    print("Network build complete")
    print(f"JSON files scanned: {total_json}")
    print(f"Docs with extracted names: {docs_processed}")
    print(f"Unique people (nodes): {len(node_doc_freq)}")
    print(f"Co-occurrence edges (weight >= {args.min_edge_weight}): {edge_count_after_filter}")
    print(f"Nodes CSV: {nodes_path}")
    print(f"Edges CSV: {edges_path}")


if __name__ == "__main__":
    main()
