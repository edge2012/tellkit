"""Single source of truth for generation, validation and renderer capabilities."""
from typing import Literal, get_args
from pydantic_core import PydanticCustomError

Action = Literal['move_to', 'split', 'merge', 'sink', 'pour', 'dissolve',
                 'appear', 'disappear', 'highlight', 'scale']
ALLOWED = get_args(Action)
SPLIT_COUNTS = (2,)
SplitCount = Literal[*SPLIT_COUNTS]
SUPPORTED = {a: dict(implemented=True) for a in ALLOWED}
SUPPORTED['split']['count'] = list(SPLIT_COUNTS)
SUPPORTED['scale']['factor'] = 1.25
SUPPORTED['highlight']['effect'] = 'yellow tint'


def validate_capability(action, count=None):
    if action not in ALLOWED or (action == 'split' and count not in SPLIT_COUNTS):
        raise PydanticCustomError('ACTION_NOT_SUPPORTED',
            'Unsupported action={action}, count={count}; supported={supported}',
            dict(action=str(action), count=str(count), supported=SUPPORTED))
