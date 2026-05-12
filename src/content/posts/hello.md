---
title: "Hello, docs-to-blog"
date: 2026-05-12
---

This is the inaugural post on a site whose entire pipeline lives between a Google Doc and a static blog. The content you're reading was written here; the layout you're seeing was assembled outside the source.

## What this proves

The pipeline can ingest a Google Doc with a separate `styling` tab, render plain markdown to a styled static site, and survive daily edits without losing the per-paragraph styling attached to each piece of writing.

A note for verification: the \<aside\>next paragraph carries\</aside\> no inline markup, yet it should render as an aside — that style assignment lives outside the source, in whichever of the two paragraph-styling artifacts (anchors.yaml or decisions.md) the pipeline is currently using.

When we first sketched the system on a napkin, the anchors were an afterthought. Now they're the load-bearing piece — or, if implementation B wins after dogfooding, they're gone entirely and the decisions file is the only audit trail.

## Affordances at a glance

Plain prose stays plain. A styled phrase can be wrapped inline with an HTML-style span tag; the tag name names the style[^1]. Footnotes ride through the gdoc CLI's markdown export untouched.

For the styling vocabulary itself, see the `styling` tab — that's where the author defines, in prose, what each named style means. Reusable styles shared across projects live in a separate library document.
