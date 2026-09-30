# Muninn Context

This file defines the canonical language used across Muninn. It is a
glossary, not an implementation specification.

## Language

**Training Pack**:
A distributable collection of training content and the plugin behavior
needed to present and judge it.
_Avoid_: quiz pack, reciting pack, study pack.

**Training Plugin**:
The executable Python component of a Training Pack. It presents
training content and judges Attempts.
_Avoid_: reciting plugin, study plugin.

**Training Session**:
One bounded period in which a user works through Training Items.
_Avoid_: study session, reciting session.

**Attempt**:
One user response to one Training Item, together with its correctness
and timing.
_Avoid_: review, answer event.
