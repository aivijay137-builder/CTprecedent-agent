# Results so far (plain English)

Updated as runs are added. Each line names the run it comes from (see `RUNS.md`).

## 9 Nov 2026: before any router code
- **The 19 draft packs are structurally sound.** All 20 files (19 packs plus the base) pass the schema: every number has its n, every rule has a rationale and evidence (R02). The validator is not a rubber stamp: six deliberately broken packs were all rejected (R03).
- **The packs are drafts with known weak spots** (R04): three era breakpoints look too early to mean anything (2005 to 2006), three packs found no breakpoint, and some packs rest many cutoff norms on fewer than 30 trials. Psoriasis is the thinnest (2 subtypes and 2 measures under 30 trials).
- **Safety baseline:** the full test suite had 95 passing tests before any router code (R05).
- **The golden snapshot is repeatable** (R06): running the prompt-only engine again on the three golden designs gives exactly the saved comparables, order, scores and flags. So a later "packs off is unchanged" test is meaningful.

## 9 Nov 2026: loader, router, merge and ranking (steps 1 and 2 of the build)
- **Unit tests (fixture packs, no registry):** 20 pass (R08). One failed on the first run because of my own wrong expectation in the era-penalty test (R07); the code was right and the test was corrected.
- **The first real-data check found a real bug the unit tests could not:** 4 of 9 designs were routed to the wrong pack (R09), for example bronchiectasis to COPD and lung cancer to blood cancers. Cause: parent terms leaked in from other conditions on the same trials. A first fix lost heart failure (R10) because old records often lack parent terms. The final rule gives **9 of 9 as expected** (R11).
- **Router on real data is now a permanent test** (R12: 29 pass; skips itself without the registry).
- **Not yet proven:** that packs improve anything, and that the prompt-only path is unchanged after the engine hooks (next).

## 9 Nov 2026: engine hooks and the guarantee
- **The prompt-only path is unchanged (R13, 6 of 6 pass).** With no pack, and with a pack whose parts are all switched off, the three golden designs return exactly the saved comparables, order, scores, flags and notes.
- **API layer works** (R18, 9 pass): pack list, route with preview, run with a pack, the decision-log row (role, pack, version, parts), compare, and error cases.
- **What the draft pack actually changes on real data (R14, R16, no AI, no verdict on quality):**
  - With era off: bronchiectasis 0 comparables swapped, heart failure 1 swapped, psoriasis 0 swapped. **No flag and no bottom line changed in any of the three.**
  - With era on (R14), 4 to 8 trials swapped, but for the wrong reasons: it penalised trials of a drug class that does not apply (so era is now off by default, D20).
  - The hard filter removed 30% of heart failure candidates (D22).
  - Plain reading: as configured the pack is a **small nudge to the order**, not a different result. Whether the nudge is an improvement is unknown.

## 9 Nov 2026: whole-suite check after the backend changes
- **Full suite: 140 passed** with the registry and packs present (R20). Before any pack code it was 95 (R05), so 45 new tests were added and none of the old ones broke.
- **As GitHub CI sees it (no registry, no pack files): 112 passed, 28 skipped, nothing failed** (R21).
- Two mistakes of mine were caught on the way and fixed (R19): the engine call shape for prompt-only runs, and a test that touched the registry at import.

## 10 Nov 2026: screens and the end-to-end check
- **The pack screens work in a real browser** (R23, screenshots in `Prompt_EVALS/screens/`): the options block, the draft warning, the four switches, the pack banner on the results, and the compare view. The compare view matches the earlier script run on the same design (0 trials swapped, 16 of 26 at the same rank).
- **Front end type-checks and builds, and so does the saved-results demo** (R22).
- **Final suite:** see the last two rows of `RUNS.md` (full suite and CI view).

## Not yet known
- **Whether packs make results better.** No quality eval exists yet (not built). Nothing above says packs help.
