"""docs-check: lint Markdown docs for broken links, missing metadata, terminology and style.

Usage:
    python docs_check.py PATH [PATH ...] [--terms terms.txt] [--format text|json]
    python docs_check.py PATH --review-prompt   # print a review prompt for an approved AI tool

Exit code is 1 when any error is found, 0 otherwise. Warnings never fail the run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REQUIRED_FIELDS = ("title", "description")
MAX_SENTENCE_WORDS = 30
# Words that tell the reader a task is easy. If it isn't easy for them, the doc has lost them.
FILLER_WORDS = ("simply", "just", "easy", "easily", "obviously", "please")

LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
INLINE_CODE_RE = re.compile(r"`[^`]*`")


@dataclass
class Finding:
    file: str
    line: int
    severity: str  # "error" or "warning"
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.severity} [{self.rule}] {self.message}"


def slugify(heading: str) -> str:
    """Turn a heading into the anchor GitHub generates for it."""
    text = INLINE_CODE_RE.sub(lambda m: m.group(0).strip("`"), heading)
    text = re.sub(r"[^\w\- ]", "", text.lower())
    return text.replace(" ", "-")


def split_front_matter(text: str) -> tuple[dict[str, str], int]:
    """Return the front matter fields and the line number where the body starts."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 1
    fields: dict[str, str] = {}
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return fields, i + 1
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip("\"'")
    return fields, 1  # no closing fence, so treat it all as body


def prose_lines(text: str, start: int):
    """Yield (line_number, line) for prose, skipping fenced code and inline code."""
    in_fence = False
    for n, line in enumerate(text.splitlines(), start=1):
        if n < start:
            continue
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield n, INLINE_CODE_RE.sub("", line)


def anchors_in(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    _, start = split_front_matter(text)
    found = set()
    for _, line in prose_lines(text, start):
        m = HEADING_RE.match(line)
        if m:
            found.add(slugify(m.group(2)))
    return found


def load_terms(path: Path | None) -> list[tuple[re.Pattern[str], str]]:
    """Read 'wrong => right' pairs. Lines starting with # are comments."""
    if path is None:
        return []
    rules = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=>" not in line:
            continue
        wrong, right = (part.strip() for part in line.split("=>", 1))
        # Case-only fixes (kubernetes => Kubernetes) must match case exactly,
        # otherwise the correct spelling would be flagged too.
        flags = 0 if wrong.lower() == right.lower() else re.IGNORECASE
        rules.append((re.compile(rf"\b{re.escape(wrong)}\b", flags), right))
    return rules


def check_file(path: Path, terms: list[tuple[re.Pattern[str], str]]) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    name = path.as_posix()
    findings: list[Finding] = []

    fields, body_start = split_front_matter(text)
    for field in REQUIRED_FIELDS:
        if not fields.get(field):
            findings.append(Finding(name, 1, "error", "metadata", f"missing front matter field '{field}'"))

    last_level = 0
    for n, line in prose_lines(text, body_start):
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            if last_level and level > last_level + 1:
                findings.append(Finding(name, n, "warning", "heading-skip",
                                        f"heading jumps from H{last_level} to H{level}"))
            last_level = level

        for alt, _ in IMAGE_RE.findall(line):
            if not alt.strip():
                findings.append(Finding(name, n, "error", "alt-text", "image has no alt text"))

        for _, target in LINK_RE.findall(line):
            findings.extend(check_link(path, name, n, target))

        for pattern, right in terms:
            for m in pattern.finditer(line):
                if m.group(0) != right:
                    findings.append(Finding(name, n, "error", "terminology",
                                            f"use '{right}' instead of '{m.group(0)}'"))

        unquoted = re.sub(r"\"[^\"]*\"", "", line)  # a quoted word is being mentioned, not used
        for word in FILLER_WORDS:
            if re.search(rf"\b{word}\b", unquoted, re.IGNORECASE):
                findings.append(Finding(name, n, "warning", "filler",
                                        f"'{word}' adds nothing or assumes the task is easy"))

        if not heading and not line.lstrip().startswith(("|", ">")):
            # Drop the list marker so "1." is not counted as a sentence of its own.
            item = re.sub(r"^\s*(?:\d+\.|[-*+])\s+", "", line)
            for sentence in re.split(r"(?<=[.!?])\s+", item):
                words = len(sentence.split())
                if words > MAX_SENTENCE_WORDS:
                    findings.append(Finding(name, n, "warning", "long-sentence",
                                            f"sentence has {words} words (limit {MAX_SENTENCE_WORDS})"))
    return findings


def check_link(path: Path, name: str, n: int, target: str) -> list[Finding]:
    if target.startswith(("http://", "https://", "mailto:")):
        return []  # external links need the network; keep this check offline
    file_part, _, anchor = target.partition("#")
    dest = (path.parent / file_part).resolve() if file_part else path
    if not dest.exists():
        return [Finding(name, n, "error", "broken-link", f"'{target}' points to a file that does not exist")]
    if anchor and dest.suffix == ".md" and anchor not in anchors_in(dest):
        return [Finding(name, n, "error", "broken-anchor", f"'{target}' has no matching heading")]
    return []


def collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        files.extend(sorted(p.rglob("*.md")) if p.is_dir() else [p])
    return files


def review_prompt(path: Path, findings: list[Finding]) -> str:
    """Build a prompt for an approved AI tool. The script never sends anything itself."""
    found = "\n".join(f"- line {f.line}: {f.message}" for f in findings) or "- none"
    return (
        "You are reviewing a product documentation topic.\n"
        "Check it against these rules and list every problem with its line number:\n"
        "1. Each step has one action, starts with a verb, and says what the reader should see after it.\n"
        "2. Prerequisites list everything the reader needs before step 1.\n"
        "3. No claim about product behavior that the topic does not support. If unsure, say so; do not guess.\n"
        "4. Plain English, short sentences, no marketing language.\n"
        "Do not rewrite the topic. A human writer will verify every suggestion against the product.\n\n"
        f"The automated checker already found:\n{found}\n\n"
        f"Topic ({path.name}):\n---\n{path.read_text(encoding='utf-8')}\n---\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint Markdown documentation.")
    parser.add_argument("paths", nargs="+", help="Markdown files or folders")
    parser.add_argument("--terms", type=Path, help="terminology file with 'wrong => right' lines")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--review-prompt", action="store_true",
                        help="print an AI review prompt for each file instead of the report")
    args = parser.parse_args(argv)

    terms = load_terms(args.terms)
    files = collect(args.paths)
    all_findings: list[Finding] = []
    for f in files:
        findings = check_file(f, terms)
        if args.review_prompt:
            print(review_prompt(f, findings))
        all_findings.extend(findings)

    if not args.review_prompt:
        if args.format == "json":
            print(json.dumps([asdict(f) for f in all_findings], indent=2))
        else:
            for f in all_findings:
                print(f)
            errors = sum(f.severity == "error" for f in all_findings)
            print(f"\n{len(files)} file(s) checked: {errors} error(s), "
                  f"{len(all_findings) - errors} warning(s)")
    return 1 if any(f.severity == "error" for f in all_findings) else 0


if __name__ == "__main__":
    sys.exit(main())
