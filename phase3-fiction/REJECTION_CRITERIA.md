# Rejection Criteria (Phase 3)

This file defines **why a chapter gets rejected**. Its purpose is to turn
the user's sense of quality into an explicit criterion the system can use.
A selection/revision loop only works with a written elimination rule;
without one, the step "write three versions and pick one" is useless too.

The criteria are written **negatively**: "reject if this happens". The
positive description of style (voice, tone, POV) is the Style Contract's
job, not this file's.

The user edits this file freely. When adding a new item, paste a real
example from a text if possible; the more concrete a criterion is, the
better it works.

---

## A. Structural Reasons (measurable)

**A1. Fragmentation.** Reject if most paragraphs in the chapter are 1-3
sentences long. A one-sentence "emphasis paragraph" can be used at most 2
times per chapter. Constantly starting a new line is not a literary rhythm,
it is risk avoidance: a long paragraph has to hold one thought up for two
hundred words, and every local inconsistency shows; fragmenting hides
that risk.

**A2. Undeveloped thought.** Reject if the chapter does not have at least
three places where one perception/memory/thought develops without a break
for at least 150 words. Depth means an idea does not end in one sentence.

**A3. Interrogation rhythm.** Reject if three or more back-to-back lines of
dialogue are one or two sentences each and no action/look/reaction comes
between them. That is not a conversation, it is an interrogation.

**A4. No long line.** Reject if there is no moment in the chapter where a
character speaks without interruption for at least 4-5 sentences. (This
rule is also in every Style Contract.)

---

## B. Style Reasons (need judgment)

**B1. Aphorism at the end of the paragraph.** The habit of ending
paragraphs on a short, closed, epigram-like sentence. Once it is striking;
in every paragraph it becomes the text's only rhetorical move and the
signature of shallowness. Examples of the pattern:

> "The kettle had always known before she did."
> "Tides keep no promises."
> "Some doors are only closed from the inside."

Reject if this move appears more than twice in the chapter.

**B2. Closed units.** Reject if every paragraph completes itself and no
sentence needs the one before it. In a good passage sentences owe each
other something; the text produces a few large thoughts that develop, not
thirty small closed ones.

**B3. Filling a quota.** Reject if a rule (long line of dialogue, moment of
warmth, hook for a term) does not grow out of the text but is met once like
ticking a box on a task list and then dropped. Compliance is not style.

**B4. Feeling without cost.** Reject if a character's feeling is named
directly, without a concrete behavior/cost that pays for it.

**B5. Riskless sentence.** Reject if the chapter does not have a single
sentence that could fail. A smooth, error-free text is not a good text;
literature is made of sentences that could fail.

---

## C. Content Reasons

**C1. Against canon.** Reject if it contradicts a permanent fact in
`canon.json` or `architecture.json`.

**C2. Unintroduced term.** Reject if a new institution/term/title/place
name is not introduced with a natural hook tied to a character in the
chapter where it first appears. The reader did not read the source files.

**C3. Constraint violation.** Reject if it contradicts
`phase2-world/CONSTRAINTS.md` or the `constraint_compliance` field of the
architecture (e.g. a supernatural object appearing in a world without
magic).

---

## Usage

When choosing between two texts, the order is: first C (content violations
are eliminated), then A (measurable structure), then B (style judgment).
If A and B are tied, **the riskier one** is chosen.
