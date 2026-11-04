# SPDX-License-Identifier: GPL-3.0-or-later
"""Update section visibility in place, preserving the board and native transitions."""
from . import localization as ui
from .workflow_state import hold_enabled, is_held


def menus(column):
    from .column_menu import column_menu
    column_menu(column.window,column.stack,button=column.get_first_child().get_last_child())
    if column.not_now:
        column_menu(column.window,column.stack,button=column.rail.get_first_child())


def visibility(column, kind, visible, create, *, animate, after_hidden=None):
    field=kind+'_section';closing_field='_closing_'+kind
    section=getattr(column,field)
    if visible:
        if section:return
        section=getattr(column,closing_field,None)
        setattr(column,closing_field,None)
        if section is None:
            section=create()
            column.body.append(section.revealer)
        if kind=='hold':
            archived=column.archived_section or getattr(column,'_closing_archived',None)
            if archived and archived.revealer.get_prev_sibling() is not section.revealer:
                column.body.reorder_child_after(section.revealer,archived.revealer.get_prev_sibling())
        elif section.revealer is not column.body.get_last_child():
            column.body.reorder_child_after(section.revealer,column.body.get_last_child())
        setattr(column,field,section)
        section.revealer.reveal(True,animate=animate)
    elif section:
        setattr(column,field,None)
        setattr(column,closing_field,section)
        def remove():
            if getattr(column,closing_field,None) is not section:return
            setattr(column,closing_field,None)
            if section.revealer.get_parent() is column.body:
                column.body.remove(section.revealer)
            if after_hidden:after_hidden()
        section.revealer.reveal(False,animate=animate,after_hidden=remove)


def refresh_archives(column, *, update_menu=True):
    from .archived_cards import ArchivedCards
    cards=column.window.filtered_cards(column.stack)
    ui.text(column.count,'text',str(len(cards)))
    animate=update_menu and column.get_mapped()
    visibility(column,'archived',column.window.shows_archived(column.stack['id']),
        lambda:ArchivedCards(column.window,column.stack,[c for c in cards if c.get('archived')],
                             triage=column.triage,flexible=column.flexible,column=column),animate=animate)
    if column.not_now:
        from .workflow_sections import apply_fold
        apply_fold(column)
    if update_menu:menus(column)


def active_cards(column):
    from .active_cards import ActiveCard
    paused=hold_enabled(column.window,column.stack['id'])
    box=column.drop.cards_box
    previous_height=column.active_revealer.get_height()
    column.drop.clear_mark()
    child=box.get_first_child()
    while child:
        following=child.get_next_sibling();box.remove(child);child=following
    widgets=[]
    for card in column.window.filtered_cards(column.stack):
        if card.get('archived') or paused and is_held(column.window,card):continue
        tile=ActiveCard(card,column.window,min_width=0 if column.flexible else 252)
        box.insert(tile,-1) if column.triage else box.append(tile)
        widgets.append(tile)
    column.drop.widgets[:]=widgets
    column.drop.held=False if paused else None
    column.active_revealer.resize_from(previous_height,animate=column.get_mapped(),closing=not paused)


def refresh_hold(column):
    from .workflow_sections import HoldSection
    enabled=hold_enabled(column.window,column.stack['id'])
    active_cards(column)
    cards=[c for c in column.window.filtered_cards(column.stack) if not c.get('archived') and is_held(column.window,c)]
    visibility(column,'hold',enabled,lambda:HoldSection(column,cards),animate=column.get_mapped())
    menus(column)
