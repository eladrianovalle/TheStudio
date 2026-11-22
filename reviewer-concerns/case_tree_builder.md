# Reviewer concerns: case_tree_builder

## 1. A plant's probe is never shown to pass on the unplanted tree

- **Concern:** the spec's plant rule 3 says "The probe fails on the planted tree and passes on the unplanted one." `prove_probe` in `studio/editor_measure.py` runs the probe once, on the built (planted) tree only. A plant whose probe also fails without the patch (a probe that is simply broken) builds and counts as a defect case.
- **Why unresolved:** out of this unit's scope. None of unit 3's six criteria asks for the unplanted run; the spec's plant checklist sits with the case set.
- **Follow-up:** in `prove_probe`, for `source == "plant"`, also run the probe on `writer_sha` alone (a throwaway checkout of the source repo, so the tree gains no objects) and refuse when it fails there; or add it as a suite check in unit 4 (`editor_case_set`).

## 2. `load_case`'s refusals have no test

- **Concern:** `load_case` refuses an unknown `kind` or `source`, empty `acceptance_criteria`, and "a defect case needs a probe that shows the defect". No test exercises any of them. The probe refusal is what stops a defect case from building with no proof its defect exists; deleting it leaves the suite green.
- **Why unresolved:** out of this unit's scope as written: unit 4's first criterion owns the case-shape checks, and per AI-TDD the assertions are a person's to own.
- **Follow-up:** one scenario test per refusal (a defect case with no `probe`, a case with `kind: "other"`, a case with `acceptance_criteria: []`), each asserting exit 1 and the case's name in the output.
