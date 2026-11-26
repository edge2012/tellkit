"""Shared recognition of children's comparative knowledge questions.

Recognition selects teaching structure; it never bypasses content safety.
"""
import re

_PATTERN = re.compile(r"(?:哪一个|哪个|哪根|哪边|哪条|谁)[^，。！？!?；;\n]{0,30}[多少大小远近快慢重轻高矮长短]")


def is_comparison(text: str) -> bool:
    return bool(_PATTERN.search(text))
