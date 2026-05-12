// @ts-check
import { defineConfig } from 'astro/config';
import remarkSpans from './src/plugins/remark-spans.ts';
import remarkAnchors from './src/plugins/remark-anchors.ts';

// Static output works directly with Vercel's GitHub integration; no adapter needed.
// Plugin order matters:
//   remarkSpans   (P3)  — text-level: rewrites `<tag>text</tag>` to `<span class="tag">…</span>`.
//   remarkAnchors (P4a) — paragraph-level: reads `styles/anchors.yaml` and attaches
//                         `<p class="…">` based on (heading, ordinal) matches.
// Spans run first so paragraph hashes in anchors.yaml are computed against text
// that hasn't yet been mutated; anchors run second so they decorate the wrapper.
export default defineConfig({
  output: 'static',
  markdown: {
    remarkPlugins: [remarkSpans, remarkAnchors],
    rehypePlugins: [],
  },
});
