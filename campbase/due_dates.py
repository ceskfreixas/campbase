# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Timezone-aware due dates shared by the editor and server verification."""
from datetime import datetime, timezone


def parse_due(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None


def same_due(first, second):
    try:
        return parse_due(first) == parse_due(second)
    except (ValueError, TypeError, AttributeError):
        return first == second


def local_due(value):
    parsed = parse_due(value)
    return parsed.astimezone() if parsed and parsed.tzinfo else parsed


def server_due(value):
    """Deck's datetime database field expects a UTC wall clock, not an offset.

    Convert before transport: merely preserving a +01:00 suffix can shift the
    stored instant when Deck serializes its timezone-less database value as UTC.
    """
    parsed = parse_due(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()
