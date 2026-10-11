#!/usr/bin/env bash
set -euo pipefail

source_dir="${1:-.agents/skills}"
destination_dir="${2:-.cline/skills}"
repo_dir="$(pwd -P)"
source_path="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$source_dir")"
destination_path="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$destination_dir")"

case "$source_path" in
  "$repo_dir"/*) ;;
  *) echo "Source must be inside this repository: $source_path" >&2; exit 1 ;;
esac

case "$destination_path" in
  "$repo_dir"/*) ;;
  *) echo "Destination must be inside this repository: $destination_path" >&2; exit 1 ;;
esac

if [[ ! -d "$source_path" ]]; then
  echo "Source skills directory does not exist: $source_path" >&2
  exit 1
fi

mkdir -p "$destination_path"
count=0
shopt -s nullglob

for skill_dir in "$source_path"/*; do
  [[ -d "$skill_dir" ]] || continue
  skill_name="$(basename "$skill_dir")"

  if [[ ! "$skill_name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    echo "Skill directory is not lowercase kebab-case: $skill_name" >&2
    exit 1
  fi

  skill_file="$skill_dir/SKILL.md"
  if [[ ! -f "$skill_file" ]]; then
    echo "Missing SKILL.md for skill: $skill_name" >&2
    exit 1
  fi

  python3 - "$skill_file" "$skill_name" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
expected_name = sys.argv[2]
text = path.read_text(encoding="utf-8")
match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
if not match:
    raise SystemExit(f"Missing YAML frontmatter: {path}")

yaml_text = match.group(1)
name_match = re.search(r"(?m)^name:\s*(.+?)\s*$", yaml_text)
description_match = re.search(r"(?ms)^description:\s*(.*?)(?=^\S|\Z)", yaml_text)
if not name_match:
    raise SystemExit(f"Missing name field: {path}")
if not description_match:
    raise SystemExit(f"Missing description field: {path}")

name = name_match.group(1).strip().strip('"').strip("'")
description = description_match.group(1).strip().strip('"').strip("'")
if name != expected_name:
    raise SystemExit(f"Skill {expected_name} has frontmatter name {name!r}")
if len(description) < 40:
    raise SystemExit(f"Skill {expected_name} has an empty or too-short description")
PY

  target="$destination_path/$skill_name"
  temp="$destination_path/.$skill_name.tmp"
  rm -rf "$temp"
  cp -a "$skill_dir" "$temp"
  rm -rf "$target"
  mv "$temp" "$target"
  echo "Synced $skill_name"
  count=$((count + 1))
done

if [[ "$count" -eq 0 ]]; then
  echo "No skill directories found in $source_path" >&2
  exit 1
fi

echo "Synced $count skills from $source_dir to $destination_dir"
