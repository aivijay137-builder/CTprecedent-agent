"""Phase C: the AI words each flag's sentence from its EVIDENCE BUNDLE only.

The bundle is the facts the rule already computed from SQL (the rule's own title, sentence, question, n and confidence).
The AI may rephrase them; it may not add any. Code then checks the result: every number, number-word and NCT ID in the
AI's sentence must already be in the bundle. If anything is new, that flag keeps its fixed template sentence.
Nothing here can change n, evidence IDs, confidence, ranking or a decision: only the `body` text, and only when the check passes.
"""
import json
import re

from . import llmsvc

VERSION = "w1"
MAX_CHARS = 420

SYSTEM = """You reword findings about a clinical-trial design into one clear, plain-English paragraph for a study lead.
The user message is JSON: {"flags": [{"id": ..., "title": ..., "facts": ..., "question": ..., "n": ...}]}. "facts" is the finished, verified sentence(s) for that flag.
Return JSON only: {"sentences": {"<id>": "<paragraph>"}} with one paragraph for EVERY id.
Rules:
- Use ONLY the facts given. Do not add any number, percentage, date, trial ID, drug, country or claim that is not in "facts", "title", "question" or "n".
- Keep every number exactly as written. Do not round, convert, add, subtract or compare numbers yourself. Do not write a number as a word.
- Do not give advice, a prediction or a cause. Describe what the data shows, then stop.
- At most 2 sentences and 60 words. Plain words. No bullet points, no headings.
- Never write an NCT ID."""

NUMBER_WORDS = {"two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "dozen", "hundred",
                "thousand", "million", "half", "quarter", "third", "double", "triple", "twice", "majority"}


def _nums(s: str) -> set[str]:
    out = set()
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", s or ""):
        m = m.replace(",", "")
        out.add(m.rstrip("0").rstrip(".") if "." in m else m)
    return out


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z]+", (s or "").lower())) & NUMBER_WORDS


def check(sentence, bundle_text: str) -> str:
    """'' if the sentence only uses what the bundle holds; otherwise the reason it was refused."""
    if not isinstance(sentence, str) or not 20 <= len(sentence.strip()) <= MAX_CHARS:
        return "wrong length or not text"
    if re.search(r"NCT\d{4,}", sentence):
        return "contains a trial ID"
    new_nums = _nums(sentence) - _nums(bundle_text)
    if new_nums:
        return f"new number(s): {sorted(new_nums)}"
    new_words = _words(sentence) - _words(bundle_text)
    if new_words:
        return f"new number word(s): {sorted(new_words)}"
    return ""


def bundle(f: dict) -> dict:
    return {"id": f["id"], "title": f["title"], "facts": f["body"], "question": f["question"], "n": f["n"]}


def reword(flags: list[dict], budget: llmsvc.Budget | None = None) -> dict:
    """Rewrites flag['body'] in place where the AI's sentence passes the check. Returns {"used": n, "refused": {id: reason}}.
    Raises llmsvc.LLMUnavailable when the AI is off, capped or down (the caller keeps the template sentences)."""
    if not flags:
        return {"used": 0, "refused": {}}
    bundles = [bundle(f) for f in flags]
    out = llmsvc.ask("write_flags", VERSION, SYSTEM, json.dumps({"flags": bundles}), budget)
    got = out.get("sentences") or {}
    used, refused = 0, {}
    for f, b in zip(flags, bundles):
        text = " ".join(str(b[k]) for k in ("title", "facts", "question", "n"))
        why = check(got.get(f["id"]), text)
        if why:
            refused[f["id"]] = why
            continue
        f["body"] = got[f["id"]].strip()
        f["written_by"] = "ai"
        used += 1
    return {"used": used, "refused": refused}
