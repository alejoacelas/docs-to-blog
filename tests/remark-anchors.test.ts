/**
 * Unit tests for the remark-anchors plugin.
 *
 * These run a minimal remark → rehype pipeline with the plugin and
 * assert that the rendered HTML carries the expected class on the
 * matched paragraph. The plugin reads `anchors.yaml` from disk; each
 * test points it at a temp file with hand-crafted content.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import rehypeRaw from 'rehype-raw';
import rehypeStringify from 'rehype-stringify';

import remarkAnchors from '../src/plugins/remark-anchors';

function hashPara(text: string): string {
  const normalised = text.replace(/\s+/g, ' ').trim();
  return createHash('sha256').update(normalised, 'utf8').digest('hex').slice(0, 8);
}

async function renderWith(md: string, anchorsPath: string): Promise<string> {
  const file = await unified()
    .use(remarkParse)
    .use(remarkAnchors, { anchorsPath })
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeStringify, { allowDangerousHtml: true })
    .process(md);
  return String(file).trim();
}

describe('remark-anchors', () => {
  let tmp: string;

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'remark-anchors-'));
  });

  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  it('injects the mapped class on a matched paragraph', async () => {
    const para = 'When we first sketched the system on a napkin.';
    const yamlText = `
paragraphs:
  - class: aside
    anchor:
      quote:
        exact: "When we first sketched"
      heading: "Why"
      ordinal: 1
      hash: "${hashPara(para)}"
`;
    const anchorsPath = join(tmp, 'anchors.yaml');
    writeFileSync(anchorsPath, yamlText);

    const md = `# T\n\n## Why\n\n${para}\n`;
    const html = await renderWith(md, anchorsPath);
    expect(html).toContain('<p class="aside">');
    expect(html).toContain('napkin');
  });

  it('does not inject when no entry matches the position', async () => {
    const yamlText = `
paragraphs:
  - class: aside
    anchor:
      quote:
        exact: "no such text"
      heading: "Why"
      ordinal: 1
      hash: "00000000"
`;
    const anchorsPath = join(tmp, 'anchors.yaml');
    writeFileSync(anchorsPath, yamlText);

    const md = `## Different\n\nA paragraph that the anchor does not address.\n`;
    const html = await renderWith(md, anchorsPath);
    expect(html).not.toContain('class="aside"');
  });

  it('skips injection when quote.exact is not in the paragraph', async () => {
    const para = 'The actual paragraph text.';
    const yamlText = `
paragraphs:
  - class: aside
    anchor:
      quote:
        exact: "something completely different"
      heading: "Why"
      ordinal: 1
      hash: "${hashPara(para)}"
`;
    const anchorsPath = join(tmp, 'anchors.yaml');
    writeFileSync(anchorsPath, yamlText);

    const md = `## Why\n\n${para}\n`;
    const html = await renderWith(md, anchorsPath);
    expect(html).not.toContain('class="aside"');
    expect(html).toContain('The actual paragraph text');
  });

  it('handles ordinal>1 under the same heading', async () => {
    const yamlText = `
paragraphs:
  - class: feature-quote
    anchor:
      quote:
        exact: "second paragraph"
      heading: "Why"
      ordinal: 2
      hash: "${hashPara('The second paragraph here.')}"
`;
    const anchorsPath = join(tmp, 'anchors.yaml');
    writeFileSync(anchorsPath, yamlText);

    const md = `## Why\n\nThe first paragraph here.\n\nThe second paragraph here.\n`;
    const html = await renderWith(md, anchorsPath);
    expect(html).toContain('<p class="feature-quote">The second paragraph here.</p>');
    // First paragraph should NOT get the class.
    expect(html).not.toContain('<p class="feature-quote">The first paragraph here.</p>');
  });

  it('handles paragraphs with empty heading (no heading above)', async () => {
    const para = 'A paragraph with no heading above it.';
    const yamlText = `
paragraphs:
  - class: aside
    anchor:
      quote:
        exact: "with no heading"
      heading: ""
      ordinal: 1
      hash: "${hashPara(para)}"
`;
    const anchorsPath = join(tmp, 'anchors.yaml');
    writeFileSync(anchorsPath, yamlText);

    const md = `${para}\n`;
    const html = await renderWith(md, anchorsPath);
    expect(html).toContain('<p class="aside">');
  });

  it('does not crash when anchors.yaml is missing', async () => {
    const md = '## Why\n\nOnly content here.\n';
    const html = await renderWith(md, join(tmp, 'nonexistent.yaml'));
    expect(html).toContain('Only content here');
    expect(html).not.toContain('class="');
  });

  it('does not crash on malformed yaml (logs a warning)', async () => {
    const anchorsPath = join(tmp, 'anchors.yaml');
    writeFileSync(anchorsPath, 'paragraphs: [\n  - class:');
    const md = '## Why\n\nContent.\n';
    const html = await renderWith(md, anchorsPath);
    expect(html).toContain('Content');
  });

  it('handles multiple anchors on different paragraphs in one run', async () => {
    const p1 = 'First paragraph here.';
    const p2 = 'Second paragraph here.';
    const yamlText = `
paragraphs:
  - class: aside
    anchor:
      quote:
        exact: "First paragraph"
      heading: "T"
      ordinal: 1
      hash: "${hashPara(p1)}"
  - class: feature-quote
    anchor:
      quote:
        exact: "Second paragraph"
      heading: "T"
      ordinal: 2
      hash: "${hashPara(p2)}"
`;
    const anchorsPath = join(tmp, 'anchors.yaml');
    writeFileSync(anchorsPath, yamlText);

    const md = `## T\n\n${p1}\n\n${p2}\n`;
    const html = await renderWith(md, anchorsPath);
    expect(html).toContain('<p class="aside">First paragraph here.</p>');
    expect(html).toContain('<p class="feature-quote">Second paragraph here.</p>');
  });
});
