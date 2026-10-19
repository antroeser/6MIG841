# Rules this kit adds

A local rules directory, read by `aider-rules-sync.py` alongside the canonical
one and merged into `rules.md`. A rule number defined in both places is a
refusal, not a merge, so nothing here can quietly override a rule from upstream.

This is also where a rule of your own goes. Write it as a bolded statement in the
same form, give it a number nobody else uses, and re-run the sync.

---

**R27 - every function carries a header a caller can act on.**
Not a restatement of the signature: a reader who cannot see the body must be able
to call it correctly and to know what happens when it fails. Five parts, in this
order, of which the first, third and fourth are mandatory:

1. **Purpose** - one or two sentences, what it does, not how.
2. **Details** - optional, and only for an algorithm or an edge case a reader
   would otherwise get wrong.
3. **Inputs** - every parameter: name, type, meaning. `None` when there are none.
4. **Outputs** - type and meaning of the return value, and any side effect
   stated here too, since a function that writes a file returns more than its
   value.
5. **Raises** - optional in general, mandatory as soon as the function raises
   deliberately. Name the exception and the condition, never the message text.

A private helper carries the same header; a one-line wrapper may carry Purpose
alone. Other languages use their own idiom - `///` for C#, JSDoc for JS and TS -
with the same five parts.

Comments inside a body explain **why**. The code already says what, so a comment
repeating the line above it is noise and one contradicting it is a defect. When a
line exists because of a measurement or a past failure, say so and give the date.

Measured 2026-09-03: this rule exists because the pipeline's own output did not
follow it. The convention lived in a `## Docstrings` section rather than a bolded
statement, so the generator could not see it, `rules.md` said nothing about
docstrings, and the only instruction the model received was "match the
surrounding code: its comment density" - which, in a fresh file, is none. Four
generated functions carried no header at all.
