# Reviewer concerns: memory_rules_sorted

## The comment above NOT_YET_ENFORCED_COUNT is now false

- **Concern:** `studio/tests/test_enforced_rules.py` still says "Rose once, on purpose, from 20 to 52 when specs/judged-rules.md sorted the rules an audit found unchecked. This number only goes down from here." The count is now 54, so both the number and "only goes down from here" are wrong.
- **Why unresolved:** out of this unit's scope. Agents write no code comments here, and the spec says a person rewords this comment at review.
- **Follow-up:** at review, the owner rewords the comment so it covers the second rise to 54 from this spec's memory sort, or deletes it.
