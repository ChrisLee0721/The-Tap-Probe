#!/usr/bin/env bash
# Assemble the single-document report from the chapter sources.
# Usage:  bash build_report.sh
# Order matters: 00_main_report.md already contains the title page, abstract, TOC,
# Chapters 1-4, References header is NOT included there; chapter files follow.
set -euo pipefail
cd "$(dirname "$0")"

OUT="EEE4483_MiniProject_Report.md"
PARTS=(
  00_main_report.md
  _chapters/ch5.md
  _chapters/ch6.md
  _chapters/ch7.md
  _chapters/ch8.md
  _chapters/ch9_10.md
  _chapters/refs.md
  _chapters/appa.md
  _chapters/appb.md
  _chapters/appc.md
  _chapters/appd.md
  _chapters/appe.md
  _chapters/appf.md
)

: > "$OUT"
for f in "${PARTS[@]}"; do
  if [ ! -f "$f" ]; then
    echo "MISSING: $f" >&2
    exit 1
  fi
  cat "$f" >> "$OUT"
done

echo "wrote $OUT  ($(wc -l < "$OUT") lines, $(wc -w < "$OUT") words)"
