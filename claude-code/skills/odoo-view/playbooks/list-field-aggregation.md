# List view field aggregation

Applies when: adding footer aggregations (sum, avg, min, max) to list view columns.

Called by: [inherit-view](inherit-view.md), [implement-view](implement-view.md)

## Usage
- used: 1
- last used: 2026-07-10

## Steps
- [ ] Only put `sum=`/`avg=`/`min=`/`max=` on float, integer, or monetary list fields — other types are silently excluded from the footer calculation with no error
- [ ] Verify the field type in the model before adding an aggregate attribute; don't assume from the displayed value

## Pitfalls
- Using aggregation on a non-numeric field (e.g., `Char`, `Selection`, `Date`): the footer silently ignores it; user sees no footer value and may assume aggregation is broken

## Example instance
- Good: `<field name="amount" sum="Total"/>`  on a `Monetary` field
- Bad: `<field name="state" sum="Count"/>` on a `Selection` field (silently ignored)

## Relevant knowledge-base

- note: XML View - List Aggregate Footer & Row Click — which field types the footer
  silently excludes.
