---
title: "Notes on slow systems"
date: 2026-05-13
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

Code review is not the only example of this. The same dynamic shows up
in onboarding, in design review, in any place where two humans have to
slow down enough to notice what the other actually means. The slowness
is the medium, not the friction.

Consider a team that buys a review summariser. The summariser does what
it promises: it reads the diff and writes a paragraph. The team starts
reading the paragraph instead of the diff. Within a quarter the place
where two engineers <aside>actually disagreed
about something</aside> has gone quiet, and nobody can quite say when.

It turns out the slowness was load-bearing. The summariser removed it
in exchange for a number on a dashboard, and only weeks later did
anyone notice that the trade had been made at all.

## What I keep getting wrong

The shape of the mistake is always the same. I see a slow process and I
optimise the most measurable part of it. Then I notice that the
unmeasurable part — the part that was doing the actual work — has
quietly evaporated.

A line I want to keep in front of me, taped to my monitor, repeated
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
