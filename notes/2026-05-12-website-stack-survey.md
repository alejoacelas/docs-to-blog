# Website stack survey: Google Doc -> markdown -> styled HTML

Date: 2026-05-12
Author: research subagent
Audience: project owner deciding on a stack for the docs-to-blog pipeline

## Problem restatement

- Google Doc is the source of truth; a cron pipeline produces a markdown file (with footnotes) outside the repo.
- The website lives in the repo and turns that markdown into HTML.
- The repo also stores **per-paragraph (ideally per-sentence) CSS overrides** that target paragraphs in the rendered output. These overrides must be version-controlled and *not* live in the doc.
- Footnotes must render correctly.
- Easy deploy to Vercel / Netlify / Cloudflare Pages / GitHub Pages.
- Site may grow beyond a blog (routes, layouts, maybe an API).

The non-obvious constraint: **styling must attach to paragraphs in markdown that the human author cannot annotate**. That rules out any approach that relies on inline attribute syntax in the markdown itself (markdown-it-attrs, rehype-attr, Hugo `{class=foo}`, Pandoc-style attributes), unless we layer a preprocessing step on top. The realistic options are:

1. A **sidecar file** in the repo (e.g. `styles.json` keyed by paragraph index or stable id) consumed by a custom remark/rehype plugin.
2. An **MDX component override** for `p` that looks up styles by index, paragraph hash, or first-N-chars match.
3. A **post-render HTML transform** (cheerio / linkedom) keyed by paragraph index, run after markdown -> HTML.

All three are feasible in every JS stack below; (1) is the cleanest because it stays in the unified pipeline and preserves source maps / position info on AST nodes.

## Findings on the rehype-attrs ecosystem

Investigated whether any off-the-shelf plugin reads paragraph attributes from a **sidecar file** rather than inline markdown. Result: **no.**

- `rehype-attr` (jaywcjlove) — inline HTML-comment syntax only (`<!--rehype:class=foo-->`). Confirmed in repo docs; no external-config option.
- `remark-attr` / `markdown-it-attrs` / `remark-attributes` — all rely on `{.class}` inline syntax in the markdown body.
- `remark-class-names` (pngwn) — accepts a `classMap` of unist-util-select selectors to class names (e.g. `'paragraph:nth-child(3)'`). The selectors can target specific paragraphs by position, but the map is a JS object, not a file. Easy to `require()` a JSON file into the map at config time. **This is the closest off-the-shelf fit.**
- `rehype-decorate` (rstacruz) — HTML-comment-based, like rehype-attr.
- `remark-flexible-paragraphs` (ipikuka) — adds className via inline `~~>` markers in the markdown body; not sidecar-driven.
- Hugo's markdown attributes — `{class="foo"}` line below the paragraph, inside the markdown. Inline only.

**Conclusion**: there is no published "sidecar attributes" plugin. The cleanest solution is a ~30-line custom remark plugin that:

1. Reads `styles.json` (or `styles.yml`) at plugin init.
2. Walks paragraph nodes with `unist-util-visit`, tracks an index, and attaches `node.data.hProperties.className` from the sidecar map.
3. Optional: hash the paragraph's text content and key the map by hash (survives reordering) instead of by index (fragile).

This plugin is **stack-agnostic** — it works in anything that wraps unified (Astro, Next.js, Eleventy via `eleventy-plugin-remark`, custom build script). Hugo is the only candidate that *cannot* host it, because Hugo's renderer is Goldmark (Go), not unified.

## On MDX with generated markdown

MDX expects the input to be valid JSX-in-markdown. Pipeline output from Google Docs will contain characters that MDX tries to parse as JSX: literal `<`, `>`, `{`, `}`, stray angle brackets in quotes, etc. Documented footgun. `next-mdx-remote` mitigates this by allowing plain `.md` mode (no MDX features) — at which point you've given up the only reason to use MDX (inline components). **Verdict: MDX is a poor fit when markdown is machine-generated** and not authored by a human who knows the JSX rules. Use plain markdown + a unified pipeline instead.

## Comparison table

Legend: + good / o ok / - bad / ! footgun

| Criterion | Astro v5 | Next.js (app) + plain MD | Eleventy | Hugo | Plain build script | Docusaurus | MkDocs |
|---|---|---|---|---|---|---|---|
| External markdown ingest (cron-written file) | + glob loader, base can be anywhere on filesystem | + read file at build or request time | + addWatchTarget / glob input | + needs file in content/, symlink or copy | + trivially | o requires file in docs/ | o requires file in docs/ |
| Daily rebuild trigger | + webhook or scheduled deploy | + ISR or cron rebuild | + cron rebuild | + cron rebuild | + cron rebuild | + cron rebuild | + cron rebuild |
| Per-paragraph CSS via sidecar | + custom remark plugin in `markdown.remarkPlugins` | + custom remark plugin via next-mdx-remote serialize or unified pipeline | + custom remark plugin via eleventy-plugin-remark, or markdown-it ruleset | - Goldmark is Go, no JS plugin host; must post-process HTML | + full control, mount any unified plugin | o possible but fighting the framework | - python plugin ecosystem, no unified |
| Footnotes | + via remark-gfm (one config line) | + via remark-gfm | + markdown-it-footnote or remark via plugin | + Goldmark footnote extension built-in | + remark-gfm | + built-in | + pymdownx.footnotes |
| Build & deploy | + static or hybrid; Vercel/Netlify/CF/GH all first-class | + Vercel native; static export works on CF/GH | + pure static, any host | + pure static, any host | + pure static, any host | + static, any host | + static, any host |
| Routing & growth | + file-based, layouts, islands, server routes available | + most powerful: app router, server actions, API routes | o filesystem routing, less ergonomic for app-like features | o filesystem routing | - DIY everything | ! docs-shaped routing; fighting it for non-docs pages | ! docs-shaped only |
| Authored in (skills mix) | TS/JS, .astro components | TS/JS, React | JS, Liquid/Nunjucks/etc | Go templates | TS/JS | TS/JS, React | Python, Jinja |
| MDX-only footguns | none if you avoid `.mdx` | ! avoid MDX path for generated content | none | none | none | ! all content is MDX | n/a |

## Recommendation

### 1st choice: Astro v5 with content collections + `glob()` loader + a custom remark sidecar plugin

Why:

- Astro 5's content loaders explicitly support **content stored anywhere on the filesystem, even outside the repo**. The `glob()` loader takes a `base` path; point it at the cron pipeline's output directory.
- `markdown.remarkPlugins` in `astro.config.mjs` accepts any unified plugin. Drop in `remark-gfm` for footnotes and a ~30-line custom plugin for sidecar styles.
- Static-by-default output deploys cleanly to all four hosting targets.
- Routing and layouts scale from "one blog page" to "complicated site" without rewriting. Server routes available when the site grows.
- Avoids MDX entirely on the content path (use `.md`, not `.mdx`), sidestepping the JSX-in-generated-markdown footgun.
- The custom plugin is small and stack-portable, so the decision is reversible.

Concrete shape:

```
content/blog/         <- written by cron pipeline (gitignored or symlinked)
styles/<slug>.json    <- in repo, version-controlled
src/content.config.ts <- defineCollection({ loader: glob({ base: '../content', pattern: '**/*.md' }) })
astro.config.mjs      <- remarkPlugins: [remarkGfm, [sidecarStyles, { dir: 'styles' }]]
```

The sidecar plugin reads `styles/<slug>.json` (passed via vfile data), walks paragraph nodes, and attaches `data.hProperties.className` either by index or by content hash. Per-sentence styling is achievable by splitting a paragraph's `text` node on sentence boundaries inside the same plugin.

### 2nd choice: plain build script (Node + unified + a tiny static-server-or-router)

Why:

- Maximum control, zero framework friction.
- One file (`build.js`) reads the cron-produced markdown, runs `unified().use(remarkParse).use(remarkGfm).use(sidecarStyles).use(remarkRehype).use(rehypeStringify)`, drops HTML into `dist/`.
- Deploys to anything. GitHub Pages works out of the box.
- Footnotes via `remark-gfm`. Sidecar plugin as in Astro.

Why not first: when the site grows beyond a blog you'll reinvent routing, layouts, dev server, image handling. The work you save up front is paid back as soon as you want a second page type. Good escape hatch / prototype path; not a destination.

### 3rd choice: Eleventy

Why:

- Pure static, deploys anywhere, very small.
- Footnotes via `markdown-it-footnote` (built-in markdown-it pipeline) or `eleventy-plugin-remark` if you want the unified ecosystem and the sidecar plugin.
- External markdown can come in via `addWatchTarget` + a glob, or by symlinking the cron output into the input directory.

Why not first:

- Default markdown engine is markdown-it, not unified. If you want the unified-based sidecar plugin (recommended), you have to switch to `eleventy-plugin-remark`, which is community-maintained and less actively developed than Astro's first-party remark integration.
- Layouts/routing are fine for a blog; less ergonomic than Astro when the site grows. No first-class component model.

## Stacks to eliminate

- **Next.js + MDX** — MDX is the wrong tool for generated markdown (JSX parse errors on stray `<`, `{`); Next.js without MDX is fine but heavier than needed and the deploy story is best on Vercel only. If you're sure you want SSR / API routes day one, reconsider — but don't pick MDX.
- **Hugo** — fast and pleasant, but Goldmark has no JS plugin host. The sidecar-styles plugin would have to be either a Go extension (high effort) or a post-build HTML rewrite step (works, but the styling logic now lives outside the markdown pipeline). Reasonable if you love Go; otherwise dominated by Astro.
- **Docusaurus** — docs-shaped routing, MDX-only content path, and React component overhead. Fighting the framework as soon as you want non-doc pages. Also reinherits the MDX-on-generated-content problem.
- **MkDocs** — Python plugin ecosystem (pymdownx etc.) is rich for docs but doesn't speak unified/remark. Sidecar styling would need a custom Python markdown extension; possible but the smallest plugin ecosystem fit of the bunch. Best when you specifically want Material-for-MkDocs aesthetics on a documentation site.

## Per-paragraph styling: implementation sketches

In order of how cleanly they meet the constraint.

### A. Custom remark plugin reading `styles/<slug>.json` (recommended)

```js
// remark-sidecar-styles.js
import { visit } from 'unist-util-visit';
import fs from 'node:fs';
import path from 'node:path';

export default function sidecarStyles({ dir }) {
  return (tree, file) => {
    const slug = path.basename(file.path, '.md');
    const map = JSON.parse(fs.readFileSync(path.join(dir, `${slug}.json`), 'utf8'));
    let i = 0;
    visit(tree, 'paragraph', (node) => {
      const rule = map[String(i)] || map[hashOf(node)];
      if (rule?.class) {
        node.data ??= {};
        node.data.hProperties ??= {};
        node.data.hProperties.className = rule.class;
      }
      i++;
    });
  };
}
```

Sidecar shape (`styles/hello.json`):
```json
{ "0": { "class": "lead" }, "3": { "class": "callout warn" } }
```

Per-sentence: same plugin walks the paragraph's children and splits text nodes on `/(?<=[.!?])\s+/`, wrapping each in a `span` with a class from `rule.sentences[i]`.

### B. MDX component override (only if you've chosen MDX anyway)

```jsx
<MDXRemote source={md} components={{ p: (props) => <p className={lookup(props)} {...props} /> }} />
```

Lookup function reads a sidecar map. Fragile because you don't have a paragraph index without writing one in; usually implemented by passing an `idx` prop via a custom remark plugin anyway — at which point you've reinvented option A.

### C. Post-render HTML rewrite (Hugo / MkDocs fallback)

Use cheerio or linkedom after the static site builds:

```js
$('article p').each((i, el) => { if (map[i]) $(el).addClass(map[i].class); });
```

Works everywhere, but the styling rule lives outside the markdown pipeline, which makes it harder to extend (e.g. per-sentence wraps).

## Open questions

1. **How are paragraphs identified between runs?** If the doc is edited and a paragraph is inserted at the top, an index-keyed sidecar silently reassigns every class. Recommend keying by a stable hash of the first ~80 chars (or the full text), with a `migrate-styles` script that prints renames. Need to decide before building.
2. **Per-sentence styling reliability** depends on sentence-splitting heuristics. Footnote-bearing sentences ("...as Smith showed.[^1]") may confuse naive `[.!?]\s` splits. Will a single fixed splitter work for this corpus, or do we need something smarter (e.g. `compromise`, `wink-nlp`)?
3. **Footnote interaction with sidecar styling.** `remark-gfm` lowers footnote references into superscript links at the end of the surrounding paragraph. If we wrap sentences in spans, we need to keep the `[^1]` reference inside the right span. Worth a 10-line spike before committing.
4. **Cron + Vercel/Netlify rebuild trigger.** Plan to use a build webhook called by the pipeline? Or commit the generated markdown into the repo and let the host rebuild on push? The latter is simpler and gives a git audit trail of content changes; the former avoids polluting git history. No info gathered here; user choice.
5. **Astro v5 dev-mode file watching on external paths.** The docs note `watcher` is available to loaders but don't confirm whether `glob()` watches paths outside the project for hot reload during dev. Likely fine for prod (cron + redeploy) but may need a manual restart in dev. Worth a 5-minute test before committing.
6. **Should `styles/<slug>.json` be human-edited or have a tooling layer?** A small UI ("open paragraph 3, pick class") would make the override workflow pleasant. Out of scope for stack choice but worth flagging.

## Sources

- [rehype-attr (jaywcjlove)](https://github.com/jaywcjlove/rehype-attr)
- [remark-class-names (pngwn)](https://github.com/pngwn/remark-class-names)
- [remark-flexible-paragraphs (ipikuka)](https://github.com/ipikuka/remark-flexible-paragraphs)
- [rehype-decorate (rstacruz)](https://github.com/rstacruz/rehype-decorate)
- [Astro markdown content guide](https://docs.astro.build/en/guides/markdown-content/)
- [Astro content loader reference](https://docs.astro.build/en/reference/content-loader-reference/)
- [Astro v5 content collections upgrade](https://docs.astro.build/en/guides/content-collections/)
- [withastro/roadmap#434 (external content)](https://github.com/withastro/roadmap/discussions/434)
- [Next.js MDX guide](https://nextjs.org/docs/app/guides/mdx)
- [hashicorp/next-mdx-remote](https://github.com/hashicorp/next-mdx-remote)
- [Hugo markdown attributes](https://gohugo.io/content-management/markdown-attributes/)
- [Eleventy: external markdown #204](https://github.com/11ty/eleventy/issues/204)
- [eleventy-plugin-remark](https://github.com/florianeckerstorfer/eleventy-plugin-remark)
- [eleventy-plugin-footnotes](https://github.com/KittyGiraudel/eleventy-plugin-footnotes)
- [Docusaurus routing](https://docusaurus.io/docs/advanced/routing)
- [Docusaurus vs MkDocs 2026](https://docsio.co/blog/docusaurus-vs-mkdocs)
