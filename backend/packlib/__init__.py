"""Therapeutic packs at run time: load (loader), choose (router), combine (merge), re-rank (rank), compare two runs (compare).
Optional by design: when no pack is chosen, none of this code runs and the engine behaves exactly as before (proven by test_packs_off_is_unchanged.py)."""
from . import compare, loader, merge, rank, router  # noqa: F401
