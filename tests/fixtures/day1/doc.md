---
title: "Notes on slow systems"
date: 2026-05-12
---

# Notes on slow systems

A small essay about the friction of building things that resist
automation. The premise is that some pieces of work are slow on purpose,
and trying to speed them up is how you lose the thing.

## Background

Every team I have worked with had at least one process that everyone
agreed should be faster, and that nobody could in fact make faster
without breaking it. Code review is the canonical example. The very act
of slowing down to read each other's work is what makes the work
trustworthy afterwards.

There is a temptation here to install a tool. The tool will summarise
the diff, the tool will suggest the change, the tool will rubber-stamp
the merge. After enough rubber-stamps the team realises it has lost the
forum it had — the place where two engineers <aside>actually disagreed
about something</aside> instead of just nodding at the CI green check.

The point is not that the tool was bad. The point is that the slowness
was load-bearing, and the tool removed it.

## What I keep getting wrong

The shape of the mistake is always the same. I see a slow process and I
optimise the most measurable part of it. Then I notice that the
unmeasurable part — the part that was doing the actual work — has
quietly evaporated.

A line I want to keep in front of me, taped to the monitor, repeated
until it sinks in: the slowness was the point, and you removed it for
the dashboard.

## Where this leaves me

I do not think the answer is to refuse all automation. The answer is
something closer to: be specific about which kind of slowness you are
removing, and which kind you are leaving in place. A code review tool
that summarises the diff is fine if the team still has the conversation
afterwards; it is corrosive if the team uses the summary as the
conversation.

This is the kind of distinction that is easy to draw on paper and hard
to draw in a Jira ticket. I do not have a tidy ending here.
