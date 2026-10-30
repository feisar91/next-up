"""Spot offensive words in text people type, for the public demo (app/demo_mode.py),
where anyone can put a name on the kiosk or an announcement on the TV.

The list is app/data/blocked_words.txt. Text is matched a word at a time, so a
name like "Cassidy" or "Hancock" isn't caught by a short word inside it. To get
past simple tricks it also checks each word with accents removed, with look-alike
digits and symbols read as letters ("sh1t", "$hit"), with stretched letters
squeezed ("fuuuck"), with a plural ending dropped, and with spaced-out letters
joined up ("f u c k").
"""
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

WORDS_FILE = Path(__file__).parent / "data" / "blocked_words.txt"

# Words on the list that are also people's names or everyday words, so blocking
# them would turn away real check-ins and harmless announcements.
ALLOWED = {
    "butt", "cumming", "domination", "escort", "hardcore", "intercourse", "kinky", "lolita", "mong",
    "negro", "playboy", "poon", "santorum", "scat", "sexual", "sexually", "sexuality", "snatch", "suck",
    "sucks", "swinger", "twinkie", "undressing", "xx",
}
# Common ones the list leaves out.
EXTRA = {
    "arse", "asshat", "bellend", "chink", "dickhead", "dickheads", "dipshit", "gook", "heil", "hitler",
    "horseshit", "kkk", "nazi", "nazis", "paedo", "pedo", "prick", "pricks", "retard", "retarded",
    "retards", "wanker", "wankers", "wog", "wogs",
}
# Blocked at the start of any word too ("shithead", "fuckwit").
PREFIXES = ("bitch", "cunt", "fagg", "fuck", "motherf", "nigg", "shit", "slut", "twat", "whore")
# Blocked anywhere, even split up by spaces or dots ("f.u.c.k", "fu ck"). Only
# ones that don't turn up inside real names.
ANYWHERE = ("faggot", "fuck", "nigga", "nigger")

LOOK_ALIKES = str.maketrans("0134578@$!|", "oieastbasii")
PLURAL_ENDINGS = ("es", "s")


@lru_cache(maxsize=1)
def _lists():
    words, phrases, symbols = set(EXTRA), set(), set()
    for line in WORDS_FILE.read_text(encoding="utf-8").splitlines():
        entry = _fold(line.strip())
        if not entry or entry.startswith("#") or entry in ALLOWED:
            continue
        if not entry.isascii():
            symbols.add(entry)  # an emoji
        elif " " in entry:
            phrases.add(" ".join(_plain_tokens(entry)))
        else:
            words.add(entry)
    return words, phrases, symbols


def _fold(text):
    """Lower case, with accents and fancy letter forms (full-width, bold) made plain."""
    text = unicodedata.normalize("NFKD", text).casefold()
    return "".join(c for c in text if not unicodedata.combining(c))


def _plain_tokens(text):
    # Keeps digits, "&" and inner hyphens, for list entries like "2g1c", "s&m", "g-spot".
    return re.findall(r"[a-z0-9&]+(?:-[a-z0-9&]+)*", text)


def _letter_tokens(text):
    return re.findall(r"[a-z]+", text.translate(LOOK_ALIKES))


def _join_spelled_out(tokens):
    """Runs of three or more single letters as one word: "f u c k" -> "fuck"."""
    joined, run = [], []
    for token in tokens + [""]:
        if len(token) == 1:
            run.append(token)
            continue
        if len(run) >= 3:
            joined.append("".join(run))
        run = []
    return joined


def _squeeze(word):
    """Every run of a repeated letter as one: "fuuuck" -> "fuck"."""
    return re.sub(r"(.)\1+", r"\1", word)


def _variants(word):
    """(forms to match whole, forms to match the start of). Fully squeezed forms
    are only matched whole: squeezing "shiitake" makes it start with "shit"."""
    stretched = {word, re.sub(r"(.)\1{2,}", r"\1\1", word)}
    whole = stretched | {_squeeze(word)}
    for form in set(whole):
        for ending in PLURAL_ENDINGS:
            if form.endswith(ending) and len(form) > len(ending) + 2:
                whole.add(form[: -len(ending)])
    return whole, stretched


def contains_blocked_word(text):
    """Whether text has a blocked word in it."""
    if not text:
        return False
    words, phrases, symbols = _lists()
    folded = _fold(text)
    if any(symbol in folded for symbol in symbols):
        return True

    letters = _letter_tokens(folded)
    for tokens in (_plain_tokens(folded), letters):
        padded = f" {' '.join(tokens)} "
        if any(f" {phrase} " in padded for phrase in phrases):
            return True
        for token in tokens + _join_spelled_out(tokens):
            whole, starts = _variants(token)
            if not whole.isdisjoint(words) or any(form.startswith(PREFIXES) for form in starts):
                return True

    run_together = "".join(letters)
    return any(word in form for form in (run_together, _squeeze(run_together)) for word in ANYWHERE)
