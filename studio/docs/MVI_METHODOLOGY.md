# Minimum Viable Interaction (MVI) Methodology

Every unit of work Studio produces — from a single task to a full roadmap — must end in a **complete, usable interaction**, not a partial component that becomes useful later.

---

## The Principle

**Not this:** wheel → axle → chassis → car (each step is useless until the last)

**Like this:** skateboard → scooter → bicycle → motorcycle → car (each step is rideable)

The key word is **Interaction**, not Product. You're not shipping incrementally toward a product — you're shipping incrementally toward richer interactions. A skateboard isn't a car, but you can ride it today.

---

## How It Applies to Studio Outputs

### Tasks End in an MVI

A task should not produce "the database schema" or "the API types" in isolation. It should produce something a user can interact with, even if crude:

- Bad: "Define the data model for user profiles"
- Good: "Users can create and view a profile (hardcoded storage, no auth)"

### Sprints End in an MVI

A sprint should not end with "backend complete, frontend next sprint." It should end with a usable interaction, even if limited:

- Bad: Sprint 1 = API endpoints, Sprint 2 = UI, Sprint 3 = integration
- Good: Sprint 1 = one flow works end-to-end (create + view), Sprint 2 = add edit + delete, Sprint 3 = add auth + polish

### Milestones End in an MVI

A milestone should be demonstrable to a stakeholder without caveats like "once we also finish X":

- Bad: M1 = architecture, M2 = core features, M3 = integration, M4 = polish
- Good: M1 = one feature works (skateboard), M2 = three features work (bicycle), M3 = full feature set (motorcycle), M4 = polished release (car)

### Roadmaps Are MVI Sequences

The roadmap is a sequence of increasingly capable MVIs. Each point on the roadmap is independently valuable. If the project is cancelled at any milestone, something usable exists.

---

## The Contrarian Test

When reviewing any plan, milestone, sprint, or task breakdown, apply this test:

> "If we stopped here, could someone use what we've built?"

If the answer is "no, they'd need to wait for the next milestone/sprint/task," the plan is building wheels, not skateboards. Reject it and demand resequencing.

---

## Enforcement in Studio Roles

- **Product** advocate must sequence milestones as MVI progressions. Contrarian rejects milestone plans where any milestone ends in an unusable state.
- **Engineering** advocate must decompose work into tasks that each produce interactable results. Contrarian rejects task lists that are "backend then frontend" or "types then logic then UI."
- **Design** advocate must define experience progressions where each tier is playable/usable. Contrarian rejects designs that require "all systems online" before any interaction works.
- **Integrator** must verify the integrated roadmap follows MVI sequencing. Each phase gate should be demonstrable.

---

## Relationship to Scoped Debate

The three-tier scoped debate (alignment → depth → polish) is itself an MVI pattern:

- **Alignment** produces a usable directional decision (skateboard)
- **Depth** produces a detailed plan with deliverables (bicycle)
- **Polish** produces a cross-checked, conflict-resolved plan (motorcycle)
- **Integrator** produces the final unified roadmap (car)

Each scope is independently valuable. If the run stops after alignment, you still have directional decisions. If it stops after depth, you have per-discipline plans.
