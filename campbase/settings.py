# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Shared supported values for persistent application preferences."""
DEFAULT_SYNC_INTERVAL = 45
SYNC_INTERVALS = (30, 45, 60, 120, 300, 600)


def sync_interval(settings):
    value = settings.get('sync_interval', DEFAULT_SYNC_INTERVAL)
    return value if value in SYNC_INTERVALS else DEFAULT_SYNC_INTERVAL


def archive_overrides(settings):
    if 'archived_overrides' in settings:
        return {str(key): value for key, value in settings['archived_overrides'].items() if isinstance(value, bool)}
    return {str(key): True for key in settings.get('archived_columns', [])}


def archives_visible(settings, stack_id):
    return archive_overrides(settings).get(str(stack_id), settings.get('show_archived_default', False))
