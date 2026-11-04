# SPDX-License-Identifier: GPL-3.0-or-later
"""Deck-backed workflow roles; only their presentation is local to this account."""


NOT_NOW_TITLES = frozenset(('ara no','not now','ahora no','agora não','orain ez','ara non'))
HOLD_TITLES = frozenset(('en espera','on hold','em espera','zain','en pausa'))


def suggested_choice(items, selected, names):
    exact = next((index for index,item in enumerate(items) if item and item['id']==selected),None)
    if exact is not None:
        return exact
    matches = [index for index,item in enumerate(items) if item and item.get('title','').casefold() in names]
    return matches[0] if len(matches)==1 else 0


def resource_choices(items, selected, names):
    values=list(items)
    existing=any(item['id']==selected or item.get('title','').casefold() in names for item in values)
    if not existing:
        return [None,*values]
    # Prefer an existing role even if several clients created matching names;
    # choosing among existing resources must never offer another duplicate.
    role=lambda item:item['id']==selected or item.get('title','').casefold() in names
    return sorted(values,key=lambda item:not role(item))


def options(store, board_id):
    metadata = store.get('board_metadata', {}).get(str(board_id), {})
    value = metadata.get('workflow', {})
    return dict(value) if isinstance(value, dict) else {}


def save_options(store, board_id, **changes):
    metadata = store.get('board_metadata', {})
    current = dict(metadata.get(str(board_id), {}))
    current['workflow'] = options(store, board_id) | changes
    metadata[str(board_id)] = current
    store.put('board_metadata', metadata)


def presentation(window, board_id):
    if board_id == window.board_id and hasattr(window, 'workflow'):
        return window.workflow
    return options(window.store, board_id)


def not_now_ids(window):
    settings = presentation(window, window.board_id)
    selected = settings.get('not_now_stack')
    if any(stack['id']==selected for stack in window.stacks()):
        return {selected}
    if 'not_now_enabled' not in settings:
        return set()
    return {stack['id'] for stack in window.stacks() if stack.get('title','').casefold() in NOT_NOW_TITLES}


def not_now_stack(window):
    settings = presentation(window, window.board_id)
    if not settings.get('not_now_enabled'):
        return None
    ids=not_now_ids(window)
    return next((stack for stack in window.stacks() if stack['id'] in ids), None)


def displayed_stacks(window):
    if presentation(window,window.board_id).get('not_now_enabled'):
        return window.stacks()
    hidden=not_now_ids(window)
    return [stack for stack in window.stacks() if stack['id'] not in hidden]


def reserved_label_ids(window, board_id=None):
    board_id = window.board_id if board_id is None else board_id
    key = presentation(window,board_id).get('hold_label')
    return {key} if key is not None else set()


def visible_labels(window, labels, board_id=None):
    reserved=reserved_label_ids(window,board_id)
    return [item for item in labels or [] if item['id'] not in reserved]


def hold_label(window, board_id=None):
    board_id = window.board_id if board_id is None else board_id
    settings = presentation(window, board_id)
    if not settings.get('hold_enabled', True):
        return None
    label_id = settings.get('hold_label')
    board = next((item for item in window.snapshot.get('boards', []) if item['id'] == board_id), {})
    return next((label for label in board.get('labels') or [] if label['id'] == label_id), None)


def hold_enabled(window, stack_id):
    return bool(hold_label(window) and stack_id in presentation(window, window.board_id).get('hold_columns', []))


def is_held(window, card):
    label = hold_label(window, card.get('boardId') or window.board_id)
    return bool(label and any(item.get('id') == label['id'] for item in card.get('labels') or []))


def held_labels(window, card, held):
    label = hold_label(window)
    labels = [item for item in card.get('labels') or [] if not label or item['id'] != label['id']]
    return labels+[label] if held and label else labels


def merge_labels(current, desired, base):
    before = {item['id'] for item in base}
    after = {item['id'] for item in desired}
    removed, added = before-after, after-before
    result = [item for item in current if item['id'] not in removed]
    present = {item['id'] for item in result}
    return result+[item for item in desired if item['id'] in added and item['id'] not in present]
