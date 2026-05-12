# gdoc CLI span-tag escaping behaviour

**Date:** 2026-05-12
**Phase:** 3 (Span Plugin) — pre-implementation empirical verification
**Question:** Does `gdoc cat --quiet <url>` preserve `<aside>text</aside>` literally, or escape the angle brackets? Where should we unescape?

## Empirical evidence

The source doc (`DOC_URL`) contains the body sentence:

> A note for verification: the <aside>next paragraph carries</aside> no inline
> markup, yet it should render as an aside — …

Pasted in the Google Doc with literal `<aside>` / `</aside>` characters (typed
as plain text, no formatting, no autocorrect). When pulled via `gdoc cat`:

```
$ set -a; source .env; set +a
$ gdoc cat --quiet "$DOC_URL" | grep '\\<'
A note for verification: the \<aside\>next paragraph carries\</aside\> no inline markup, …
```

The `gdoc` CLI (via Pandoc-style markdown export) escapes every `<` and `>`
that would otherwise be parseable as inline HTML by prefixing a backslash.
Other punctuation (commas, em dashes, `[^1]`) is untouched.

This matches the Phase 2 smoke-test observation that prompted this note.

## Decision

**Unescape in `sync/fetch.py`, immediately after `gdoc cat` returns**, before
the markdown is written to `src/content/posts/`. The remark plugin sees
canonical `<aside>...</aside>` syntax and never has to know that the upstream
exporter escapes it.

The regex is intentionally narrow:

```python
re.sub(r"\\<(/?[a-z][a-z0-9-]*)\\>", r"<\1>", markdown)
```

- Only `\<` / `\>` pairs that wrap a CSS-class-shaped tagname (lowercase
  letter followed by lowercase letters / digits / hyphens — the same shape as
  `[a-z][a-z0-9-]*` enforced by the CSS validators in P2) are unescaped.
- Stray `\<` or `\>` elsewhere in prose (e.g. an inequality `5 \< 6`) is left
  alone.
- Self-closing tags or unmatched `\<tag` openers without a corresponding
  closer would not match this exact pattern; they're handled (or
  passed-through) downstream in the remark plugin.

## Rationale (why fetch.py, not the plugin)

1. **Single source of truth for "raw" markdown.** Once `src/content/posts/*.md`
   is on disk, it is canonical: anyone reading it (Astro, vitest, a human
   diffing the PR) sees `<aside>` instead of `\<aside\>`. The plugin's
   contract becomes "transform `<tag>...</tag>` text into spans" without
   any gdoc-specific quirk knowledge.
2. **Symmetry with the PR review workflow.** The PR diff that authors review
   shows clean tags, not escape soup. Easier to spot intent.
3. **Testability.** The unescape is a pure string transform — trivial unit
   test (`tests/test_fetch_unescape.py`) with hand-crafted inputs, no live
   gdoc dependency.
4. **Plugin stays platform-agnostic.** If we ever switch markdown sources
   (Notion, Markdown files committed by hand, a different gdoc exporter)
   the plugin doesn't need to change.

## Nested-tag handling

We did not need a separate Doc round-trip to verify nested tags: gdoc's
escape rule applies uniformly per `<` / `>` character. A literal
`<aside>see <em>here</em></aside>` in the Doc would emerge as
`\<aside\>see \<em\>here\</em\>\</aside\>`, and the regex above unescapes
each pair independently, leaving canonical markdown. The remark plugin
then handles the nesting at AST level (outer pair becomes a span; inner
markdown — including `<em>` — is re-visited).
