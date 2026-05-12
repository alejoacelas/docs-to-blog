# Day 2 — what changed from day 1

The styling tab and library are byte-identical to day 1. All four edit
kinds happen in `doc.md`. They exercise the four cases PLAN §9.1 calls
out, with reference to where they hit the day 1 anchors.

## Day 1 anchors (recap)

| class           | heading                     | ord | first words                                    |
|-----------------|-----------------------------|-----|------------------------------------------------|
| `feature-quote` | Background                  | 3   | "The point is not that the tool was bad."     |
| `aside`         | What I keep getting wrong   | 2   | "A line I want to keep in front of me…"       |

There is also one inline-span anchor in the source itself (not in
`anchors.yaml`): `Background` ord=2 carries `<aside>actually disagreed
about something</aside>` inside its body. That span lives in the doc
text and travels with the paragraph however the prose is rewritten.

## Day 2 edits

### Edit 1 — Typo fix (1-word change)
**Targets** the `aside` anchor at `What I keep getting wrong` ord=2.

The line "taped to **the** monitor" becomes "taped to **my** monitor".
Hash flips `d935704c` → `0e8f1cd6`. The paragraph still lives at the
same `(heading, ordinal)`. The fuzzy matcher's `quote.exact` from day 1
is no longer a verbatim substring of the day-2 doc; Claude (Call 2) is
expected to rewrite the anchor with a substring drawn from the new
paragraph.

The expected anchor is updated to:
- `quote.exact`: "A line I want to keep in front of me, taped to my monitor"
- `hash`: `0e8f1cd6`

### Edit 2 — Inserted paragraph (ordinals shift)
A new paragraph is inserted as `Background` ord=2: "Code review is not
the only example of this…". This pushes every later `Background`
paragraph down by one:
- old ord=2 (with `<aside>` span) → new ord=3
- old ord=3 (`feature-quote` callout) → new ord=4

A correct day-2 anchors.yaml therefore lists the callout under
`Background` ord=4, not ord=3.

### Edit 3 — Rewritten paragraph that had a styled span
**Targets** `Background` ord=2 on day 1 (now ord=3 after Edit 2).

The original prose was "There is a temptation here to install a tool.
The tool will summarise the diff…". On day 2 the surrounding prose is
rewritten: "Consider a team that buys a review summariser. The
summariser does what it promises…". The inline `<aside>actually
disagreed about something</aside>` span is **preserved** in the new
prose — the span content survives the rewrite because the author kept
the substantive idea.

This paragraph never carried a paragraph-level anchor (it only had an
inline span), so `anchors.yaml` is unaffected. The span survives via
the source markup, processed by `remark-spans` at build time. The
fixture is the test that the inline-span affordance is decoupled from
the anchors mechanism.

### Edit 4 — Rewritten paragraph that was a callout
**Targets** the `feature-quote` anchor at `Background` ord=3 on day 1
(now ord=4 after Edit 2).

The original callout was "The point is not that the tool was bad. The
point is that the slowness was load-bearing, and the tool removed it."
On day 2 the paragraph is rewritten substantially: "It turns out the
slowness was load-bearing. The summariser removed it in exchange for a
number on a dashboard, and only weeks later did anyone notice that the
trade had been made at all."

The new prose still reads as a callout — a single declarative idea
pulled out for emphasis — so a defensible day-2 anchors.yaml keeps the
`feature-quote` class. (A different defensible call: drop the class
because the prose is more discursive than the original. The fixture
encodes the keep-the-class choice; the test asserts only that the
goldens themselves are valid, not that Claude would pick the same
option deterministically.)

The expected anchor is updated to:
- `quote.exact`: "It turns out the slowness was load-bearing."
- `heading` / `ordinal`: Background / 4 (ordinal shifted by Edit 2)
- `hash`: `67365bfa`

## What the fixture covers

| edit kind                                  | day-1 anchor moved? | day-1 fingerprint salvageable? | day-2 expectation |
|--------------------------------------------|---------------------|--------------------------------|---------------------|
| Typo fix                                   | yes (same position) | quote.exact no, hash no        | fuzzy matcher hits same para; LLM rewrites anchor |
| Inserted paragraph (ordinal shift)         | yes (ord 3→4)        | quote.exact no (or yes, by luck) | LLM moves anchor to new ord  |
| Rewritten paragraph w/ inline span         | no anchor exists    | n/a                            | span survives via source markup |
| Rewritten callout paragraph                | yes (full rewrite)   | quote.exact no, hash no        | LLM decides keep-or-drop class; expected: keep |
