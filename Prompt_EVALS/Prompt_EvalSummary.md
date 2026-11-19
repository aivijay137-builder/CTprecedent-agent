# Eval summary: everything we did and what it showed

Written in plain English. It explains every step recorded in the `EVALS` folder, from 9 to 10 November 2026.
The details are in `RUNS.md` (25 runs, with a link to the full output of each) and `DECISIONS.md` (29 decisions).

---

## The short version

1. We built **19 draft "pack" files**, one for each therapeutic area. A pack is a set of hints for a medical area, such as heart or lung. We checked that they are well formed.
2. We then built the **machinery to use a pack**: a router that picks a pack, a merge that combines packs, and a ranking step that re-orders the comparable trials.
3. We made it **optional**. By default, nothing changes. The design lead can switch a pack on for one run, and then press **Compare** to see the result with and without it.
4. We **proved that the normal path is unchanged** when no pack is chosen.
5. We tested on **real registry data** and found real bugs. All of them were fixed.
6. **The honest result:** on the three designs we tried, a pack changed the list of comparable trials very little, and it did not change any flag. We cannot yet say whether a pack makes results *better*, because the test needed for that has not been built.

---

## How the record is kept

Everything is stored in the `EVALS` folder so nothing is lost.

| File | What it holds |
|---|---|
| `DECISIONS.md` | Every decision: who made it, why, what else was considered, which run supports it |
| `RUNS.md` | Every test run: what it checks, the command, pass or fail |
| `runs/` | The full output of each run |
| `RESULTS.md` | A short summary of what the results mean |
| `EvalSummary.md` | This file |
| `golden/`, `results/`, `screens/`, `scripts/` | The saved snapshot, the comparison data, screenshots, and the scripts behind the runs |
| `record.py` | A small tool that runs a test and writes it into the log automatically |

**Failed runs are kept on purpose.** Five of the 25 runs failed when first run. We kept them, because they show what went wrong and how it was fixed.

---

## Stage 1: Checking the 19 draft packs (runs R01 to R04)

**What a pack is.** A pack is a config file for one medical area. It holds some wording to help the AI read eligibility text, some typical numbers for that area (trial size, length, how often trials stop), and some hints for ranking trials.

**R01: How the packs were made.** The packs were built from the registry using database queries only. No AI was used and no money was spent. Every number in a pack comes from the registry and shows how many trials it rests on. The wording is mine, written from general knowledge. It is labelled **draft, not reviewed by an expert**.

**R02: Are the files well formed?** A checker went through all 20 files (19 packs plus a base file). It requires that every number has its trial count, and that every rule explains why it exists. **Result: all 20 pass.**

**R03: Can the checker actually fail?** A checker that always says "pass" is useless. So we made six deliberately broken packs: a number with no trial count, a rule with no reason, and so on. **Result: all six broken packs were rejected.** The checker works.

**R04: A quality review across all 19 packs.** It looked for weak spots. **Result: it found several, and we noted them.**
- Three proposed "era" years looked too early to mean anything (2005 and 2006).
- Three packs found no era year at all.
- Some packs rest several numbers on fewer than 30 trials. Psoriasis is the thinnest.

*What this means:* the packs are tidy and honest about their limits, but they are first drafts.

---

## Stage 2: Safety nets before touching the app (runs R05 and R06)

Before changing any app code, we made sure we could prove we had not broken anything.

**R05: The test suite as it was.** The app's existing tests, run before any change. **Result: 95 passed.** This is the starting point.

**The golden snapshot.** We saved exactly what the app returns today, with no pack, for three designs: bronchiectasis, heart failure and psoriasis. We saved the trials, their order, their scores and the flags. The AI was switched off, so the answer is repeatable. We used a local copy of the registry that does not change.

**R06: Is the snapshot repeatable?** We ran the app again on the same three designs and compared. **Result: identical.** So the snapshot is a fair yardstick.

*Important limit:* the golden snapshot only answers "did we change the normal results?". It says **nothing about which results are better**. There are no right answers in it.

---

## Stage 3: Building the router, merge and ranking (runs R07 and R08)

We built the new code in its own folder, separate from the main app. Then we tested it with small made-up packs and a fake registry.

**R07: First run: 19 passed, 1 failed.** The failure was a **mistake in my test**, not in the code. The test expected the wrong number of penalised trials. The code was right.

**R08: After correcting the test: all 20 pass.**

*What this covers:* choosing a pack from a condition, combining area and indication packs, removing a trial only through the one hard filter, relaxing that filter when too few trials remain, and keeping the engine's own scores unchanged on screen.

---

## Stage 4: Testing on real data (runs R09 to R12)

Tests with made-up data passed. Real data told a different story.

**R09: Choosing a pack for nine real designs. 4 of 9 were wrong.**
- Bronchiectasis was sent to the COPD pack.
- Heart failure was sent to metabolic and endocrine.
- Lung cancer was sent to blood cancers.
- Glaucoma was sent to metabolic.

**Why:** the router looks at "parent" medical terms. Many trials list several conditions, so the parent terms of *other* conditions leaked in.

**R10: First fix: 1 of 9 still wrong.** We required a parent term to appear on at least 90% of a sample of trials. This fixed most cases but **lost heart failure completely**. Old trial records often have no parent terms. Only 42% of the 50 oldest heart failure trials had one, compared with 95% overall.

**R11: Second fix: 9 of 9 correct.** We now use a random sample of 200 trials and a 60% bar.

**R12: Made permanent.** The nine real-design checks became a standing test (29 tests pass). It skips itself on a machine that has no registry.

*The lesson:* the made-up tests all passed while the real data exposed the bug. Routing has to be tested on real data.

---

## Stage 5: Connecting to the app, and the key guarantee (run R13)

We added small, optional hooks into the engine. Every new input defaults to "no pack", which is exactly today's behaviour.

**R13: The guarantee test. 6 of 6 pass.** With no pack, and also with a pack whose parts are all switched off, the three golden designs return **exactly** the saved snapshot: the same trials, the same order, the same scores, the same flags.

*What this means:* turning packs on is a choice. The normal path is untouched.

---

## Stage 6: What does a pack actually change? (runs R14 to R17)

This is the first look at the real effect. It used the three golden designs, with the AI off, so it was free. **It describes what changed. It does not judge whether the change is good.**

**R14: First look, with the "older trial" penalty on.**
- The penalty pushed down many trials for the wrong reason. For bronchiectasis it penalised 11 of 26 trials for starting before 2014, a drug class that does not apply to bronchiectasis. For heart failure it penalised 233 of 315 candidates.
- **Decision (D20):** the older-trial penalty is now its own switch and is **off by default**.

**R15: A failed run.** Making that change broke two of my own tests, which still expected the old behaviour.

**R16: The same look with the penalty off.**

| Design | Comparables swapped | Flags changed |
|---|---|---|
| Bronchiectasis | 0 (16 of 26 at the same rank) | None |
| Heart failure | 1 | None |
| Psoriasis | 0 (30 of 30 at the same rank) | None |

**R17: Tests updated: 36 pass.**

*What this means:*
- As configured, a pack is a **small nudge to the order**, not a different result.
- The "same subtype" boost applies to almost every trial (24 of 26, then 250 of 261), so it separates nothing.
- The drug-versus-device filter is the only step that really removes trials. It removed 30% of heart failure candidates (95 of 315). An expert should confirm that is right.
- **We do not know yet whether the nudge is an improvement.**

---

## Stage 7: The server's pack features (run R18)

**R18: 9 of 9 pass.** These tests cover listing the packs, suggesting a pack with a preview of what it would add, running a design with a pack, recording the choice in the decision log (with time, role, pack, version and switches), comparing two runs, and handling errors such as an unknown pack.

---

## Stage 8: The whole test suite (runs R19 to R21)

**R19: 139 passed, 1 failed.** I had changed how the engine is called for **every** run, and that broke an existing test. The fix was to keep the old call for no-pack runs, because "the normal path is unchanged" includes how it is called. We did **not** change the old test to hide the problem.

**A second mistake, found in a "GitHub view" test run.** My guarantee test connected to the registry too early. On a machine without the registry (such as GitHub's test machines) it would crash instead of skipping. I fixed this so it loads only when needed.

**R20: 140 passed.** That is the original 95 plus 45 new tests. None of the old ones broke.

**R21: The GitHub view: 112 passed, 28 skipped, none failed.** The 28 skipped are the tests that need the registry or the pack files. They skip themselves, as intended.

---

## Stage 9: The screens (runs R22 and R23)

**R22: The front end builds.** The type-check passes, and so do the normal build and the saved-results demo build. The demo is not affected, because it never shows packs.

**R23: A real browser check, done by hand** (screenshots are in `screens/`):
1. **Options block:** it defaults to **Prompt only**, and says a Respiratory pack is available.
2. **Choosing a pack:** an amber "Draft pack, not reviewed by an expert" notice appears. The lead can pick the area and indication pack and tick four switches: prompt add-on, ranking hints, drug-versus-device filter, and older-trial penalty (off). There is a link to read the add-on text.
3. **Results:** a banner shows the pack, a "draft, not reviewed" badge and what it did, plus a **Compare with prompt only** button.
4. **Compare:** it runs the same design again without the pack, then shows both results side by side. For bronchiectasis it said the same 26 trials appear in both, 16 at exactly the same rank, and the flags are the same. It also says it shows **what changed, not which is better**. This matches the earlier script result.

---

## Stage 10: The final checks (runs R24 and R25)

- **R24:** full suite, **140 passed**.
- **R25:** the GitHub view, **112 passed, 28 skipped**.

---

## Mistakes that were caught (and why that is good)

| What went wrong | Where it was caught | What happened |
|---|---|---|
| My test expected the wrong number of penalised trials | R07 | The test was corrected. The code was right. |
| The router sent designs to the wrong packs on real data | R09 and R10 | Fixed with a random sample and a 60% bar (R11). |
| The era penalty penalised trials for the wrong reason | R14 | Made a separate switch, off by default. |
| Two tests still expected the old behaviour | R15 | Tests updated. |
| I changed how the engine is called for every run | R19 | Restored the old call for no-pack runs. |
| A test touched the registry too early | GitHub-view run | Now loads only when needed. |

---

## What we know and what we do not

**We know:**
- The packs are well formed, and the checker can really fail.
- The normal (prompt-only) path is **unchanged** when no pack is chosen.
- The router now picks the expected pack for nine real designs.
- A design lead can switch a pack on or off, per run, and compare the two results.
- On three designs, the pack changed 0 to 1 of the listed trials and **no flags**.

**We do not know yet:**
- Whether a pack makes results **better**. That needs the quality test (not built): hand-graded comparable trials, and a back-test against trials whose stop reasons are known.
- Whether the **prompt add-on** helps the AI read eligibility text. All these runs had the AI switched off, so that part has not been tested.
- Whether the drug-versus-device filter and the era years are right. An expert must review them.

---

## Decisions that most need your attention

- **D21:** the ranking hints change very little. Do we strengthen them, drop the subtype boost, or wait for the quality test? I suggest waiting.
- **D22:** the drug-versus-device filter removes real trials, so an expert should confirm it.
- **D20:** the older-trial penalty is off by default. The era years are drafts, and three look too early.
- **D28:** nothing is deployed. The live site has no pack files, so it shows no pack options.

## What comes next

1. Decide whether to commit and push the router code. The live site would not change visibly.
2. Build the **quality test** (not built). It is the only thing that can show whether packs help.
3. Ask a domain expert to review one pack, for example cardiovascular, as a sample.
