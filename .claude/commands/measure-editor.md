---
description: "Use when a change to the forge editor or its benchmark needs a recorded measurement."
disable-model-invocation: true
---

Start this command in a fresh worktree of the branch being measured, with full git history and no code index. The user's invocation authorizes one Workflow run.

1. From that worktree's root run `python studio/editor_measure.py build`. Stop on failure. Use the absolute runner path printed by the successful build.
2. Launch the Workflow tool by `scriptPath` using that built runner and no args. Wait for completion.
3. Run `python studio/editor_measure.py record`. If the run is void, report the named cases and reason. A new measurement starts with a fresh build.
4. Run `python studio/editor_measure.py rule --run <workflow-id>`. Put each pending case's defect and editor evidence to the user. Record each answer with `python studio/editor_measure.py rule --run <workflow-id> --case <tree-name> --outcome caught|missed --note "<reason>"`. Quote arguments safely.
5. Report the missed defects, false alarms, and the comparison to the recorded mark. For the baseline pair also report the spread. The user chooses the mark once the baseline evidence has been checked.
