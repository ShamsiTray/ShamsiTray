<!-- Keep it short. AGENTS.md has the conventions: atomic commits, a fix or
     feature landing with its tests, and any doc the change makes true riding
     along with it instead of arriving separately. -->

## What changed and why

<!-- A short paragraph. Name the behaviour in app terms; leave the file list to
     the diff. Link the issue or PR row this came from when there is one. -->

## How it was verified

- [ ] `python -m ruff check src/ tests/ run.py` is clean
- [ ] `pytest` passes
- [ ] The new tests fail with the fix reverted
- [ ] Manual checklist in `AGENTS.md` §8 for whatever the suite cannot reach

## Notes for the reviewer

<!-- Anything non-obvious: a tradeoff, a deliberate non-fix, follow-up work. -->
