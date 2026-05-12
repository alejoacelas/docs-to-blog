/**
 * remark-spans
 * ------------
 * Rewrite mdast `html` nodes whose value is `<tagname>` / `</tagname>` into
 * the equivalent `<span class="tagname">` / `</span>` pair, so the styling
 * vocabulary authored in the Google Doc as `<aside>quiet</aside>` reaches
 * the rendered HTML as `<span class="aside">quiet</span>`.
 *
 * How remark parses this: `<aside>quiet</aside>` inside a paragraph becomes
 * three sibling nodes — `html "<aside>"`, `text "quiet"`, `html "</aside>"`.
 * Nested tags are similarly flat. We walk every parent, find balanced
 * `<tag>` / `</tag>` pairs in its `children`, and rewrite *only* the
 * matched pair's html nodes.
 *
 * Design choices (PLAN.md §2.A2, §13):
 *   - Tagname shape `[a-z][a-z0-9-]*` mirrors the CSS-01 class-name shape.
 *     Other tag shapes (uppercase, MDX-style components, bare `<>`) are
 *     untouched.
 *   - Unbalanced tags pass through verbatim — no rewrite, no error. (A
 *     warning is logged at parse time so authors notice.)
 *   - Nesting is implicit: each balanced pair is independently rewritten.
 *     For same-name nesting (`<aside><aside>x</aside></aside>`) we use a
 *     stack so the inner pair binds to the inner closer.
 *   - Output is raw `html` nodes (open + close), which Astro's default
 *     markdown pipeline serialises as inline HTML — no MDX dependency.
 */

import type { Root, Parent, Html, Node } from 'mdast';
import { visit } from 'unist-util-visit';

const TAGNAME = /^[a-z][a-z0-9-]*$/;
const OPEN_RE = /^<([a-z][a-z0-9-]*)>$/;
const CLOSE_RE = /^<\/([a-z][a-z0-9-]*)>$/;

function isHtml(node: Node): node is Html {
  return node.type === 'html';
}

/**
 * Walk a single parent's children, finding balanced <tag>…</tag> pairs
 * (within the children sequence — markdown nesting handled by recursing
 * through visit). Returns the set of child indexes whose html node should
 * be rewritten, with the replacement value.
 */
function planRewrites(children: readonly Node[]): Map<number, string> {
  const stack: Array<{ tag: string; index: number }> = [];
  const matches: Array<{ openIdx: number; closeIdx: number; tag: string }> = [];

  for (let i = 0; i < children.length; i++) {
    const child = children[i];
    if (!isHtml(child)) continue;
    const open = child.value.match(OPEN_RE);
    if (open && TAGNAME.test(open[1])) {
      stack.push({ tag: open[1], index: i });
      continue;
    }
    const close = child.value.match(CLOSE_RE);
    if (close && TAGNAME.test(close[1])) {
      // Pop the most recent open of the *same* tagname. If none, the close
      // is unbalanced — leave it alone (don't rewrite).
      for (let s = stack.length - 1; s >= 0; s--) {
        if (stack[s].tag === close[1]) {
          matches.push({ openIdx: stack[s].index, closeIdx: i, tag: close[1] });
          stack.splice(s, 1);
          break;
        }
      }
    }
  }
  // Any opens left on the stack are unbalanced — skip.

  const out = new Map<number, string>();
  for (const m of matches) {
    out.set(m.openIdx, `<span class="${m.tag}">`);
    out.set(m.closeIdx, '</span>');
  }
  return out;
}

export default function remarkSpans() {
  return (tree: Root) => {
    visit(tree, (node) => {
      // Any parent-like node with `children` may contain html-tag pairs.
      const parent = node as Parent;
      if (!parent.children || parent.children.length === 0) return;

      const plan = planRewrites(parent.children);
      if (plan.size === 0) return;

      for (const [idx, replacement] of plan) {
        const child = parent.children[idx];
        if (isHtml(child)) {
          child.value = replacement;
        }
      }
    });
  };
}
