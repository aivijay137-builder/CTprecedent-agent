# User flow

**User:** trial design lead or feasibility lead at a sponsor. **Goal:** before a protocol is final, see how close past trials designed the same thing, and where this design looks unusual.

```mermaid
flowchart TD
    A[1. New design form<br/>paste criteria, or load by NCT ID] --> B[2. Confirm screen]
    B --> B1[Check condition, phase, endpoint,<br/>enrollment, control arm, countries]
    B --> B2[Review the cutoffs read from the criteria<br/>edit any value]
    B --> B3[Pick design elements to check]
    B --> B4[Pick pack options: none, or a suggested pack]
    B1 & B2 & B3 & B4 --> C[3. Run<br/>progress steps stream in]
    C --> D{4. At least 5 comparables?}
    D -- no --> E[Insufficient: no flags, reason shown]
    D -- yes --> F[Results: comparables, outcomes, flags<br/>each with n and NCT IDs]
    F --> G[5. Per flag: accept or defer]
    G --> H[Re-run after removing a comparable<br/>or editing a cutoff]
    G --> I[6. Build package, send for review]
    H --> F
```

## Steps
| # | Screen | What the user does | What the system does |
|---|---|---|---|
| 1 | New design form | Pastes the draft design and criteria, or loads a registry trial by NCT ID | `/api/briefs/parse` or `/api/briefs/from-nct` turns it into a structured brief |
| 2 | Confirm | Fixes required fields, edits cutoffs, ticks elements to check | Nothing runs until the user confirms |
| 2a | Confirm: how the criteria are read | Default: free rule reader. Optional: adds their own API key under "AI key" for the AI reader | Rule reader finds fewer limits (24% strict recall vs 63%); key is sent per request, never stored |
| 2b | Confirm: pack options | None (default), or the suggested therapeutic-area pack, or another pack of their choice | `/api/packs/route` suggests, never decides; draft status shown |
| 3 | Run | Waits | SQL finds comparables and builds every number; AI (if on) only rewords finished sentences |
| 4 | Results | Reads comparables, outcomes, flags | Under 5 comparables: "insufficient", no flags |
| 5 | Flags | Accepts or defers each flag | Decision logged with role and time |
| 6 | Re-run, package | Removes a comparable or edits a cutoff and re-runs; builds a package for a reviewer | Re-run returns a diff; reviewer decisions are recorded on the package |
| 7 | Compare (packs only) | Views with-pack vs without-pack results side by side | Shows what changed, not which is better |

## Where the user chooses
- **How criteria are read:** rule reader (default) or AI reader (own key). A pack can be added to either.
- **What gets checked:** the design elements, and any comparable they exclude.
- **What counts:** each flag is accepted or deferred by the user; the AI never closes one.
