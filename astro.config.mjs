// @ts-check
import { defineConfig } from 'astro/config';

// Static output works directly with Vercel's GitHub integration; no adapter needed.
// Remark/rehype plugins are intentionally absent here — wired in Phases 3 and 4a.
export default defineConfig({
  output: 'static',
  markdown: {
    remarkPlugins: [],
    rehypePlugins: [],
  },
});
