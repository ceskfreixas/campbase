# SPDX-License-Identifier: GPL-3.0-or-later
"""Deck-native dependency links with scoped, confirmed and idempotent writes."""
from .i18n import _


def dependency_ids(card):
    from .deck import DeckError, ServiceUnavailable
    values = card.get('dependentCards')
    if values is None:
        raise ServiceUnavailable(_("Aquest servidor encara no admet les dependències de targetes."))
    if not isinstance(values, list):
        raise DeckError(_("No s'han pogut llegir les dependències."))
    if any(type(value) is not int or value <= 0 for value in values):
        raise DeckError(_("No s'han pogut llegir les dependències."))
    return list(dict.fromkeys(values))


class CardDependenciesAPI:
    def card_dependencies(self, board_id, stack_id, card_id):
        card = self.get_card(board_id, stack_id, card_id)
        dependency_ids(card)
        return card

    def set_card_dependency(self, board_id, stack_id, card_id, target_id, present):
        from .deck import ConflictError, DeckError, OfflineError
        if type(target_id) is not int or target_id <= 0 or (present and target_id == card_id):
            raise DeckError(_("Tria una altra targeta per a la dependència."))
        board = self.check_board(board_id)
        current = self.card_dependencies(board_id, stack_id, card_id)
        if (board.get('archived') or board.get('deletedAt') or current.get('archived')
                or current.get('deletedAt') or current.get('stackId') != stack_id
                or not board.get('permissions', {}).get('PERMISSION_EDIT', False)):
            raise ConflictError(_("No es poden modificar les dependències d'aquesta targeta."))
        if (target_id in dependency_ids(current)) == present:
            return current
        target = self.request('GET', f'/cards/{target_id}', internal=True)
        if not isinstance(target, dict) or target.get('id') != target_id or target.get('deletedAt'):
            raise ConflictError(_("La targeta dependent ja no està disponible."))
        path = self.card_path(board_id, stack_id, card_id)+f'/dependentCards/{target_id}'
        try:
            self.request('POST' if present else 'DELETE', path)
        except OfflineError:
            confirmed = self.card_dependencies(board_id, stack_id, card_id)
            if (target_id in dependency_ids(confirmed)) == present:
                return confirmed
            raise
        result = self.card_dependencies(board_id, stack_id, card_id)
        if (target_id in dependency_ids(result)) != present:
            raise DeckError(_("Deck no ha confirmat el canvi de dependència. Actualitza la llista abans de repetir-lo."))
        return result
