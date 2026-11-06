"""URL slug utility module."""
import unicodedata


def slugify(text: str) -> str:
    """Turn a text string into a URL slug.

    Lowercase the text, preserve letters and digits from any script, and preserve
    Unicode combining marks (such as Arabic tanween, tashkeel, and harakat) when
    they follow a preserved letter or digit. Runs of whitespace, punctuation,
    symbols, and underscores ('_') are treated as separators and collapsed into
    a single hyphen ('-'). Leading and trailing hyphens are stripped.

    Raises:
        TypeError: If text is not a string.
        ValueError: If the resulting slug is empty (nothing left to slug).
    """
    if not isinstance(text, str):
        raise TypeError("Input must be a string")

    text = text.lower()
    out = []
    prev_kept = False

    for ch in text:
        cat = unicodedata.category(ch)
        if ch.isalnum():
            out.append(ch)
            prev_kept = True
        elif cat in ("Mn", "Mc") and prev_kept:
            out.append(ch)
        else:
            if out and out[-1] != "-":
                out.append("-")
            prev_kept = False

    slug = "".join(out).strip("-")
    if not slug:
        raise ValueError("nothing left to slug")

    return slug
