# SPDX-License-Identifier: GPL-3.0-or-later
"""Confirmed board recovery, label administration and bounded attachment I/O."""
import mimetypes
import re
import uuid
from urllib.request import Request
from urllib.error import URLError, HTTPError
from .i18n import _

MAX_ATTACHMENT = 64*1024*1024


def attachment_name(item):
    extended = item.get('extendedData')
    extended = extended if isinstance(extended, dict) else {}
    info = extended.get('info')
    info = info if isinstance(info, dict) else {}
    value = info.get('name') or info.get('basename')
    if not value:
        value = info.get('filename', '') + ('.'+info['extension'] if info.get('extension') else '')
    value = value or item.get('data') or str(item.get('id') or '')
    name = str(value).replace('\\', '/').rsplit('/', 1)[-1].replace('\r', '').replace('\n', '').replace('\0', '')
    return name if name and name not in {'.', '..'} else 'attachment'


class DeckResources:
    def restore_board(self, board_id):
        from .deck import DeckError, NotFoundError
        try:
            board = self.check_board(board_id)
            if not board.get('deletedAt'):
                return board
        except NotFoundError:
            pass
        self.request('POST', f'/boards/{int(board_id)}/undo_delete')
        board = self.check_board(board_id)
        if board.get('deletedAt'):
            raise DeckError(_("Deck no ha confirmat la restauració del tauler."))
        return board

    def manage_label(self, board_id, original, *, title=None, color=None, delete=False):
        from .deck import DeckError, ConflictError
        board = self.check_board(board_id)
        if not board.get('permissions', {}).get('PERMISSION_MANAGE', False):
            raise DeckError(_("No tens permís per gestionar les etiquetes del tauler."))
        current = next((x for x in board.get('labels') or [] if x['id'] == original['id']), None)
        if current is None:
            if delete:
                return board
            raise ConflictError(_("L'etiqueta ja no és al tauler. Torna a carregar-les."))
        if any(current.get(k) != original.get(k) for k in ('title', 'color')):
            raise ConflictError(_("L'etiqueta ha canviat a Deck. Revisa-la abans de desar."))
        path = f'/boards/{int(board_id)}/labels/{int(original["id"])}'
        if delete:
            self.request('DELETE', path)
        else:
            title, color = title.strip(), color.lstrip('#').upper()
            if not title or len(title) > 100 or not re.fullmatch(r'[0-9A-F]{6}', color):
                raise DeckError(_("Revisa el nom i el color de l'etiqueta."))
            if title != current['title'] or color != current['color'].upper():
                self.request('PUT', path, {'title': title, 'color': color})
        result = self.check_board(board_id)
        saved = next((x for x in result.get('labels') or [] if x['id'] == original['id']), None)
        if (delete and saved is not None) or (not delete and (not saved or saved['title'] != title or saved['color'].upper() != color)):
            raise DeckError(_("Deck no ha confirmat el canvi d'etiqueta. Torna a carregar-les."))
        return result

    def attachments(self, board_id, stack_id, card_id):
        from .deck import DeckError
        card = self.get_card(board_id, stack_id, card_id)
        if type(card.get('attachmentCount')) is int and card['attachmentCount'] == 0:
            return []
        result = self.request('GET', self.card_path(board_id, card['stackId'], card_id)+'/attachments', version='1.1')
        if not isinstance(result, list) or any(not isinstance(x, dict) or (type(x.get('id')) is not int or x['id'] <= 0) for x in result):
            raise DeckError(_("No s'han pogut llegir els adjunts."))
        return [x for x in result if not x.get('deletedAt')]

    def upload_attachment(self, board_id, stack_id, card_id, filename, data, before_send=lambda: None):
        from .deck import DeckError
        board = self.check_board(board_id)
        if not board.get('permissions', {}).get('PERMISSION_EDIT', False):
            raise DeckError(_("No tens permís per modificar aquesta targeta."))
        card = self.get_card(board_id, stack_id, card_id)
        if len(data) > MAX_ATTACHMENT:
            raise DeckError(_("El fitxer supera el límit de 64 MiB."))
        filename = attachment_name({'data': filename}).replace('"', '_')
        boundary = 'Campbase'+uuid.uuid4().hex
        mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\nfile\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="data"\r\n\r\n\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n').encode()+data+f'\r\n--{boundary}--\r\n'.encode()
        before_send()
        result = self.request('POST', self.card_path(board_id, card['stackId'], card_id)+'/attachments', body,
                              version='1.1', content_type='multipart/form-data; boundary='+boundary, timeout=120)
        if not isinstance(result, dict) or (type(result.get('id')) is not int or result['id'] <= 0):
            raise DeckError(_("No s'ha pogut confirmar l'adjunt. Revisa'l abans de repetir l'enviament."))
        return result

    def download_attachment(self, card_id, attachment_id, kind='deck_file'):
        from .deck import DeckError
        # Modern attachments use Files share IDs, not legacy Deck attachment IDs.
        if kind not in {'file', 'deck_file'}:
            raise DeckError(_("No s'ha pogut descarregar l'adjunt."))
        request = Request(f'{self.server}/index.php/apps/deck/cards/{int(card_id)}/attachment/{kind}:{int(attachment_id)}',
                          headers={'Authorization': self._auth, 'OCS-APIRequest': 'true'})
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read(MAX_ATTACHMENT+1)
        except (HTTPError, URLError, OSError):
            raise DeckError(_("No s'ha pogut descarregar l'adjunt.")) from None
        if len(data) > MAX_ATTACHMENT:
            raise DeckError(_("El fitxer supera el límit de 64 MiB."))
        return data
