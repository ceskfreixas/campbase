# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from campbase.task_progress import task_progress, _cached_count


class TaskProgressTests(unittest.TestCase):
    def test_counts_nested_bulleted_and_numbered_tasks(self):
        self.assertEqual(task_progress('- [x] Done\n- [ ] Pending\n  - [X] Nested\n\n1. [ ] Ordered'), (2, 4))

    def test_ignores_code_escaped_and_inline_boxes(self):
        text = 'Text [x] example\n\n```md\n- [x] Code\n```\n\n    - [ ] Indented code\n\n- \\[x] Escaped\n\n- [ ] Actual'
        self.assertEqual(task_progress(text), (0, 1))

    def test_empty_and_plain_lists_have_no_indicator(self):
        for text in (None, '', '- Plain\n- List', '☑ Plain glyph', '[ ] Not a list'):
            self.assertEqual(task_progress(text), (0, 0))

    def test_edits_change_the_count_and_rebuilds_reuse_it(self):
        _cached_count.cache_clear()
        self.assertEqual(task_progress('- [ ] Task'), (0, 1))
        self.assertEqual(task_progress('- [x] Task'), (1, 1))
        self.assertEqual(task_progress('- [ ] Task'), (0, 1))
        self.assertEqual(_cached_count.cache_info().hits, 1)

    def test_long_descriptions_do_not_fill_the_cache(self):
        _cached_count.cache_clear()
        self.assertEqual(task_progress('- [x] Task\n\n'+'a'*32768), (1, 1))
        self.assertEqual(_cached_count.cache_info().currsize, 0)
