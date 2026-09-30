# Training Groups

A training group combines selected question types from one or more
installed packs. For example, a group may enable the "number to element"
question type from the chemistry pack and the "kana to romaji" question
type from a Japanese pack.

## Persistence

Groups and the active Textual theme are stored in:

```text
~/.muninn/config.json
```

A group stores only opaque hashes for its pack and question-type
references. Raw paths and user-provided identifiers are resolved against
the installed catalog before a session starts.

Each selection may include a `weight`. The current UI creates selections
with weight `1.0`; the field is retained so future scheduling policies can
apply per-type weighting without a configuration migration.

## Scheduling

All enabled question types contribute `ProblemRef` values to one global
scheduler. The scheduler receives:

- host-owned attempt statistics;
- the group selection weight;
- pack and question-type identity;
- optional metadata supplied by `describe_problem()`.

Scheduling policy therefore stays independent of the pack that produced a
problem. Plugins never manipulate the host queue directly.

## Ownership

The pack that contributes a problem owns:

- statement rendering;
- answer checking;
- expected answer formatting;
- expansion or explanation text.

The host owns:

- scheduling and queue state;
- answer persistence;
- group composition;
- state routing between packs.

## CLI

```bash
muninn group list
muninn group run <group_id_or_name>
```

The Textual group builder is opened with `g` from the pack library.
Press `/` to search packs, groups, and question types through Textual's
command palette, `Enter` to toggle a question type in the Tree,
`Ctrl+S` to save, and `Ctrl+R` to start.
