# SPDX-License-Identifier: GPL-3.0-or-later
"""Count Markdown tasks locally, excluding code and escaped checkbox text."""
from functools import lru_cache
import mistune

PARSER = mistune.create_markdown(renderer='ast', plugins=['task_lists'])


def _count(description):
    pending = list(PARSER(description))
    completed = total = 0
    while pending:
        token = pending.pop()
        if token['type'] == 'task_list_item':
            total += 1
            completed += bool(token.get('attrs', {}).get('checked'))
        pending.extend(token.get('children', []))
    return completed, total


_cached_count = lru_cache(maxsize=256)(_count)


def task_progress(description):
    if not isinstance(description, str) or not any(marker in description for marker in ('[ ]', '[x]', '[X]')):
        return 0, 0
    return _cached_count(description) if len(description) <= 32768 else _count(description)
