"""Text metrics shared by the writing and review stages."""

import re

_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]")
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")


def count_words(text: str) -> int:
    """Count English words or use the existing character count for Chinese prose."""
    if _HAN.search(text):
        return len(text.replace(" ", "").replace("\n", ""))
    return len(_WORD.findall(text))
