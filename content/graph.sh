#!/usr/bin/env bash
shopt -s globstar nullglob

MDFILES=$(find . -maxdepth 1 -type f -name '*.md')
for i in "${!MDFILES[@]}"; do
    MDFILES[$i]="${MDFILES[$i]:2:-3}"
done

for md in "${MDFILES[@]}"; do
    for graph in resources/"$md"/*.gv; do
        dot -Tsvg "$graph" -o "images/$md/$(basename "$graph" .gv).svg"
    done
done