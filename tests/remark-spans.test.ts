/**
 * Unit tests for the remark-spans plugin.
 *
 * Each case asserts on the *rendered HTML* produced by a minimal
 * remark → rehype pipeline. That's the same shape Astro emits for
 * content-collection posts (see node_modules/@astrojs/markdown-remark
 * createMarkdownProcessor — uses `remarkRehype` with
 * `allowDangerousHtml`, plus `rehypeRaw`).
 */

import { describe, it, expect } from 'vitest';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import rehypeRaw from 'rehype-raw';
import rehypeStringify from 'rehype-stringify';

import remarkSpans from '../src/plugins/remark-spans';

async function render(md: string): Promise<string> {
  const file = await unified()
    .use(remarkParse)
    .use(remarkSpans)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeStringify, { allowDangerousHtml: true })
    .process(md);
  return String(file).trim();
}

describe('remark-spans', () => {
  it('rewrites a simple <tag>text</tag> into <span class="tag">text</span>', async () => {
    const html = await render('A note: <aside>quiet</aside> here.\n');
    expect(html).toContain('<span class="aside">quiet</span>');
    expect(html).not.toContain('<aside>');
  });

  it('handles nested differently-named tags', async () => {
    const html = await render('Mix: <aside>see <em>here</em> later</aside>.\n');
    expect(html).toContain(
      '<span class="aside">see <span class="em">here</span> later</span>',
    );
  });

  it('emits a span even when no CSS class with that name exists', async () => {
    const html = await render('Outlier: <doesnotexist>x</doesnotexist>.\n');
    expect(html).toContain('<span class="doesnotexist">x</span>');
  });

  it('leaves unbalanced openers verbatim (pass-through, no error)', async () => {
    const html = await render('Broken: <aside>oops with no closer\n');
    // The unbalanced opener stays as <aside>; we just need to not crash and
    // to not produce a span around something we didn't match.
    expect(html).toContain('<aside>');
    expect(html).not.toContain('<span class="aside">');
  });

  it('leaves bare wrappers like <> alone', async () => {
    const html = await render('Bare: a <> wrapper or <>x</> stays as-is.\n');
    expect(html).not.toContain('<span class="">');
    expect(html).not.toContain('<span>');
  });

  it('expands multiple spans in a single paragraph', async () => {
    const html = await render(
      'Two: <feature-quote>A</feature-quote> then <aside>B</aside>.\n',
    );
    expect(html).toContain('<span class="feature-quote">A</span>');
    expect(html).toContain('<span class="aside">B</span>');
  });

  it('accepts hyphens and digits in tagnames', async () => {
    const html = await render('Hyphen: <feature-quote-2>x</feature-quote-2>.\n');
    expect(html).toContain('<span class="feature-quote-2">x</span>');
  });

  it('leaves uppercase tagnames alone (CSS-class shape only)', async () => {
    const html = await render('Component: <Foo>x</Foo>.\n');
    expect(html).not.toContain('<span class="Foo">');
  });

  it('handles same-name nesting via the stack (outer closer binds outer opener)', async () => {
    const html = await render('Deep: <aside><aside>x</aside></aside>.\n');
    // Both pairs match — inner-opens close to inner-closes, outer to outer.
    expect(html).toContain(
      '<span class="aside"><span class="aside">x</span></span>',
    );
  });

  it('does not rewrite an isolated close tag', async () => {
    const html = await render('Only close: </aside> on its own.\n');
    // rehype-raw may strip the orphan close tag from the final HTML; what
    // we assert is that the plugin didn't synthesise a phantom span around
    // unmatched content.
    expect(html).not.toContain('<span class="aside">');
    expect(html).not.toContain('</span>');
  });

  it('rewrites spans inside list items', async () => {
    const html = await render('- one <aside>note</aside> two\n- three\n');
    expect(html).toContain('<span class="aside">note</span>');
  });

  it('rewrites spans inside headings', async () => {
    const html = await render('## A <aside>side</aside> heading\n');
    expect(html).toContain('<span class="aside">side</span>');
  });

  it('is a no-op on markdown with no tags', async () => {
    const html = await render('Plain paragraph with no tags.\n');
    expect(html).toBe('<p>Plain paragraph with no tags.</p>');
  });
});
