// @ts-check
import { defineConfig } from 'astro/config';
import remarkSpans from './src/plugins/remark-spans.ts';

// Static output works directly with Vercel's GitHub integration; no adapter needed.
// remarkSpans (P3) rewrites `<tag>text</tag>` literals into `<span class="tag">…</span>`.
export default defineConfig({
  output: 'static',
  markdown: {
    remarkPlugins: [remarkSpans],
    rehypePlugins: [],
  },
});
