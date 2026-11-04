# SPDX-License-Identifier: GPL-3.0-or-later
"""Confirm a normal Deck stack before assigning it a local workflow role."""
from .i18n import _


class WorkflowAPI:
    def ensure_not_now_stack(self, board_id, title):
        from .deck import ConflictError, DeckError, OfflineError
        board = self.check_board(board_id)
        if (board.get('archived') or board.get('deletedAt')
                or not board.get('permissions', {}).get('PERMISSION_MANAGE', False)):
            raise ConflictError(_("No tens permís per crear columnes en aquest tauler."))
        from .workflow_state import NOT_NOW_TITLES
        names = NOT_NOW_TITLES | {title.casefold()}
        def matches(stacks):
            found = [item for item in stacks if not item.get('deletedAt') and item.get('title', '').casefold() in names]
            if len(found) > 1:
                raise ConflictError(_("Hi ha diverses columnes amb aquest nom. Tria la columna que vols utilitzar."))
            return found[0] if found else None
        stacks = self.request('GET', f'/boards/{board_id}/stacks')
        existing = matches(stacks)
        if existing:
            return existing
        try:
            result = self.create_stack(board_id, title, max((item.get('order', 0) for item in stacks), default=-1)+1)
        except OfflineError:
            existing = matches(self.request('GET', f'/boards/{board_id}/stacks'))
            if existing:
                return existing
            raise
        if not isinstance(result, dict) or type(result.get('id')) is not int or result['id'] <= 0:
            raise DeckError(_("No s'ha pogut confirmar la columna nova. Sincronitza abans de tornar-ho a provar."))
        return result


    def ensure_hold_label(self, board_id, title, *, board=None):
        from .deck import ConflictError, OfflineError
        from .workflow_state import HOLD_TITLES
        board = self.check_board(board_id) if board is None else board
        names = HOLD_TITLES | {title.casefold()}
        def existing(current):
            matches = [item for item in current.get('labels') or [] if item.get('title','').casefold() in names]
            if len(matches)>1:
                raise ConflictError(_("Hi ha diverses etiquetes d'espera. Tria l'etiqueta que vols utilitzar."))
            return matches[0] if matches else None
        match = existing(board)
        if match:
            return match
        if (board.get('archived') or board.get('deletedAt')
                or not board.get('permissions',{}).get('PERMISSION_EDIT',False)):
            raise ConflictError(_("No tens permís per gestionar les etiquetes del tauler."))
        try:
            return self.create_label(board_id,title,'E9AD0C')
        except OfflineError:
            match = existing(self.check_board(board_id))
            if match:
                return match
            raise
