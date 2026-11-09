"""Every flag threshold in ONE place. Change a number here and the rule changes; nothing else needs editing.

How to read this file:
  n          = how many trials a claim is computed over (the "evidence base"). A flag always reports its n.
  strength   = how many trials directly support the claim. Used only to rank flags (see RANKING).
"""

# ---------------------------------------------------------------- applies to every flag
MIN_N = 5  # minimum trials in the evidence base. Fewer than this = no flag. Also: fewer than MIN_N comparables = no flags at all.

# ---------------------------------------------------------------- ranking
MAX_FLAGS = 3  # show at most this many flags, strongest first
# Strength ties are broken in this order (first wins).
TIE_ORDER = ["population", "sites", "endpoints", "design", "size"]

# ---------------------------------------------------------------- 1. POPULATION
# Fires when, on a parsed numeric cutoff (any condition), the design is STRICTER than at least this share of the comparables
# that state that cutoff, AND the comparables as strict or stricter than the design were stopped for slow enrollment more often
# than the looser ones.
POPULATION_STRICTER_SHARE = 0.75
# Skipped (and the reason is shown in the result) when the criteria have no numeric cutoff, or fewer than MIN_N comparables
# have that cutoff parsed.

# ---------------------------------------------------------------- 2. SITES
# Fires when at least this many OTHER trials of the same condition are recruiting or not yet recruiting with a site in
# one of the design's countries.
SITES_MIN_TRIALS = 10
SITES_STATUSES = ("RECRUITING", "NOT_YET_RECRUITING")
# Only trials whose status was verified within this many months before the data-as-of date are counted.
SITES_STATUS_VERIFIED_MONTHS = 12

# ---------------------------------------------------------------- 3. ENDPOINT
# A comparable counts as using a "similar" primary endpoint when its primary outcome mentions at least ENDPOINT_MIN_SHARED of the
# draft endpoint's ENDPOINT_KEYWORDS most distinctive words (the condition's own words are ignored).
ENDPOINT_KEYWORDS = 3
ENDPOINT_MIN_SHARED = 2
# Fires when EITHER fewer than this share of the comparables used a similar endpoint ...
ENDPOINT_SIMILAR_MAX_SHARE = 0.20
# ... OR the completed comparables with a similar endpoint posted results less often than this share (needs MIN_N such trials).
ENDPOINT_RESULTS_MIN_SHARE = 0.50

# ---------------------------------------------------------------- 4. DESIGN
# Fires when at least DESIGN_MIN_STOPPED comparable stopped with a why-stopped text mentioning one of these words,
# AND the design has a control arm (types below). If the design does not say, the rule is skipped and says so.
DESIGN_TERMS = ("placebo", "ethic", "control arm")  # "ethic" also matches ethics / ethical / ethics committee
DESIGN_TERMS_LABEL = "placebo, ethics or a control arm"  # how the terms are written in the flag text
DESIGN_MIN_STOPPED = 2
DESIGN_STOP_STATUSES = ("TERMINATED", "WITHDRAWN", "SUSPENDED")
# ClinicalTrials.gov arm-group types that count as "a placebo or comparable control arm".
DESIGN_CONTROL_ARMS = ("PLACEBO_COMPARATOR", "SHAM_COMPARATOR", "ACTIVE_COMPARATOR", "NO_INTERVENTION")

# ---------------------------------------------------------------- 5. SAMPLE SIZE (demoted)
# Fires as a flag ONLY when the target is at least this many times the largest ACTUAL enrollment among completed comparables
# (needs MIN_N completed comparables with an enrollment number). Otherwise the numbers appear only in "Element by element".
SIZE_TARGET_VS_MAX_RATIO = 2.0

# ---------------------------------------------------------------- risk pill (not a flag)
# Risk = number of non-site flags, plus 1 if comparables ended in termination more often than the condition's baseline x this factor.
RISK_TERMINATION_EXCESS = 1.25
# 0 -> low, 1..RISK_MEDIUM_MAX -> medium, above that -> high.
RISK_MEDIUM_MAX = 2
