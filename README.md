---
title: docs-check
description: A Python linter for Markdown documentation that catches broken links, missing metadata, terminology errors and style problems.
---

# docs-check

docs-check is a linter for Markdown documentation. It finds the problems a reviewer would otherwise catch by hand: broken links, missing metadata, wrong product terms and hard-to-read sentences. It runs offline, needs only the Python standard library, and returns a non-zero exit code on errors, so it can block a pull request in a docs-as-code pipeline.

## What it checks

| Rule | Severity | What it catches |
|---|---|---|
| `metadata` | error | Front matter without a `title` or `description` |
| `broken-link` | error | A relative link to a file that does not exist |
| `broken-anchor` | error | A link to a heading that does not exist, in the same file or another one |
| `terminology` | error | A term that breaks the terminology list, such as `kubernetes` instead of `Kubernetes` |
| `alt-text` | error | An image with no alt text |
| `heading-skip` | warning | A heading that jumps a level, such as H2 to H4 |
| `long-sentence` | warning | A sentence longer than 30 words |
| `filler` | warning | Words like "simply" and "just", which assume the reader finds the task trivial |

The checker skips fenced code blocks and inline code, so a command such as `kubectl get pods` is not flagged.

## Requirements

- Python 3.10 or later

## Run the checker

1. Clone the repository and open the `docs-check` folder.
2. Run the checker on a file or a folder:

   ```bash
   python docs_check.py examples/bad-topic.md --terms terms.txt
   ```

   The output lists each problem with its line number, followed by a summary:

   ```text
   examples/bad-topic.md:1: error [metadata] missing front matter field 'description'
   examples/bad-topic.md:9: error [terminology] use 'Kubernetes' instead of 'kubernetes'
   ...
   1 file(s) checked: 8 error(s), 3 warning(s)
   ```

3. To pass the results to another tool, add `--format json`.

## Edit the terminology list

`terms.txt` holds one rule per line in the form `wrong => right`:

```text
kubernetes => Kubernetes
click on => click
```

If the two forms differ only in case, the rule matches case exactly. Otherwise it ignores case.

## Use it with an AI reviewer

`--review-prompt` prints a prompt for each file instead of the report. The prompt holds the review rules, the checker's findings and the topic text. Paste it into an AI tool your team has approved.

```bash
python docs_check.py examples/bad-topic.md --terms terms.txt --review-prompt
```

The script never calls an AI service itself, so no content leaves your machine unless you choose to send it. The prompt tells the model to list problems, not rewrite the topic, and to say when it is unsure. A writer still checks every suggestion against the product before publishing.

## Run in CI

The exit code is 1 when the run finds any error, so a CI step fails on errors and passes on warnings:

```yaml
- name: Check docs
  run: python docs-check/docs_check.py docs/ --terms docs-check/terms.txt
```

## Run the tests

```bash
python -m unittest -v
```
