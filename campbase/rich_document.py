# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Render Deck Markdown into native text tags and serialize edited content."""
from . import localization as ui
import re
import mistune
from mistune.renderers.markdown import MarkdownRenderer
from gi.repository import Pango

PARSER = mistune.create_markdown(renderer="ast", plugins=["strikethrough", "table", "task_lists", "url"])
FORMATS = ("bold", "italic", "strike", "underline", "code")
DELIMITERS = {"bold": ("**", "**"), "italic": ("_", "_"), "strike": ("~~", "~~"), "underline": ("<u>", "</u>")}



class RichDocument:
    def _insert(self, text, tags=()):
        start = self.buffer.get_char_count()
        self.buffer.insert(self.buffer.get_end_iter(), text)
        for tag in tags:
            self.buffer.apply_tag_by_name(tag, self.buffer.get_iter_at_offset(start), self.buffer.get_end_iter())

    def set_markdown(self, source):
        self.loading = True
        for node in self.image_nodes:
            widget = node["widget"]
            if widget.get_parent() is self.view:
                self.view.remove(widget)
        self.image_nodes = []
        ui.text(self.buffer, 'text', "")
        self.original = source or ""
        tokens, state = PARSER.parse(self.original)
        self._blocks(tokens, state)
        # Renderers use terminal newlines; the serialized document controls them.
        while self.buffer.get_char_count() and self.buffer.get_slice(self.buffer.get_iter_at_offset(self.buffer.get_char_count()-1), self.buffer.get_end_iter(), True) == "\n":
            self.buffer.delete(self.buffer.get_iter_at_offset(self.buffer.get_char_count()-1), self.buffer.get_end_iter())
        self.loading = False
        self.modified = False

    def _blocks(self, tokens, state, prefix=""):
        for token in tokens:
            kind = token["type"]
            if kind in {"paragraph", "block_text", "heading"}:
                if prefix:
                    self._insert(prefix)
                start = self.buffer.get_char_count()
                self._inlines(token.get("children", []))
                if kind == "heading":
                    level = min(token.get("attrs", {}).get("level", 1), 3)
                    self.buffer.apply_tag_by_name("h"+str(level), self.buffer.get_iter_at_offset(start), self.buffer.get_end_iter())
                self._insert("\n\n" if kind in {"paragraph", "heading"} else "\n")
            elif kind == "list":
                ordered = token.get("attrs", {}).get("ordered", False)
                start = token.get("attrs", {}).get("start", 1)
                for index, item in enumerate(token.get("children", []), start):
                    marker = f"{index}. " if ordered else "• "
                    if item["type"] == "task_list_item":
                        marker += "☑ " if item.get("attrs", {}).get("checked") else "☐ "
                    children = item.get("children", [])
                    for child_index, child in enumerate(children):
                        if child["type"] == "list":
                            self._blocks([child], state, prefix+"  ")
                        else:
                            self._blocks([child], state, prefix+(marker if child_index == 0 else " "*len(marker)))
                if not prefix:
                    self._insert("\n")
            elif kind == "block_quote":
                self._blocks(token.get("children", []), state, prefix+"❯ ")
            elif kind == "block_code":
                name = "codeblock-" + str(len(self.code_blocks))
                raw = token.get("raw", "").removesuffix("\n")
                marker = "`" * max(3, 1 + max([len(m[0]) for m in re.finditer(r"`+", raw)] or [0]))
                self.code_blocks[name] = (marker, token.get("attrs", {}).get("info", ""))
                self.buffer.create_tag(name, family="monospace")
                self._insert(raw, (name,))
                self._insert("\n\n")
            elif kind == "blank_line":
                continue
            else:
                # Preserve tables, HTML and other advanced Markdown literally.
                raw = MarkdownRenderer().render_tokens([token], state)
                self._insert(raw.rstrip("\n"), ("literal",))
                self._insert("\n\n")

    def _inlines(self, tokens, formats=()):
        active = list(formats)
        html_styles = {"b": "bold", "strong": "bold", "i": "italic", "em": "italic", "u": "underline", "s": "strike", "del": "strike"}
        for token in tokens:
            kind = token["type"]
            style = {"strong": "bold", "emphasis": "italic", "strikethrough": "strike"}.get(kind)
            if style:
                self._inlines(token.get("children", []), tuple(active)+ (style,))
            elif kind in {"text", "codespan"}:
                self._insert(token.get("raw", ""), tuple(active)+( ("code",) if kind == "codespan" else ()))
            elif kind in {"softbreak", "linebreak"}:
                self._insert("\n", active)
            elif kind == "inline_html":
                match = re.fullmatch(r"<(/?)(b|strong|i|em|u|s|del)>", token.get("raw", ""), re.I)
                if match:
                    tag = html_styles[match[2].lower()]
                    if match[1]:
                        active = [s for s in active if s != tag]
                    elif tag not in active:
                        active.append(tag)
                else:
                    self._insert(token.get("raw", ""), active)
            elif kind == "link":
                name = "link-" + str(len(self.links))
                self.links[name] = token["attrs"]["url"]
                self.buffer.create_tag(name, underline=Pango.Underline.SINGLE, foreground="#3584e4")
                self._inlines(token.get("children", []), tuple(active)+(name,))
            elif kind == "image":
                alt = "".join(c.get("raw", "") for c in token.get("children", []))
                self.insert_image(token["attrs"]["url"], alt)
            else:
                self._insert(token.get("raw", ""), active)

    def _inline_markdown(self, start, end):
        chars, formats = [], []
        images = {n["anchor"]: n for n in self.image_nodes if not n["anchor"].get_deleted()}
        it = start.copy()
        while it.compare(end) < 0:
            anchor = it.get_child_anchor()
            if anchor and anchor in images:
                node = images[anchor]
                alt = node["alt"].replace("[", "\\[").replace("]", "\\]")
                chars.append(f"![{alt}]({node['url']})"); formats.append(())
            else:
                chars.append(it.get_char())
                names = [t.get_property("name") for t in it.get_tags()]
                formats.append(tuple([n for n in names if n in self.links] + [n for n in FORMATS if n in names]))
            it.forward_char()
        # Linear passes keep large descriptions responsive.
        left, right, nearest = [], [set() for _unused in chars], set()
        for char, styles in zip(chars, formats):
            left.append(nearest)
            if not char.isspace():
                nearest = set(styles)
        nearest = set()
        for i in range(len(chars)-1, -1, -1):
            right[i] = nearest
            if not chars[i].isspace():
                nearest = set(formats[i])
        for i, char in enumerate(chars):
            if char.isspace():
                formats[i] = tuple(f for f in formats[i] if f in left[i] & right[i])
        fence = "`" * (1 + max([len(m[0]) for m in re.finditer(r"`+", "".join(chars))] or [0]))
        def delimiters(name):
            if name in self.links:
                return "[", "](<" + self.links[name].replace(">", "%3E") + ">)"
            if name == "code":
                return fence, fence
            return DELIMITERS[name]
        result, active = [], ()
        for char, desired in zip(chars, formats):
            common = 0
            while common < min(len(active),len(desired)) and active[common] == desired[common]:common += 1
            result.extend(delimiters(s)[1] for s in reversed(active[common:]))
            result.extend(delimiters(s)[0] for s in desired[common:])
            if len(char) == 1 and "code" not in desired and char in "\\*_`[]":
                char = "\\" + char
            result.append(char)
            active = desired
        result.extend(delimiters(s)[1] for s in reversed(active))
        return "".join(result)

    def get_markdown(self):
        if not self.modified:
            return self.original
        lines = []
        count = self.buffer.get_line_count()
        code_open = None
        for line in range(count):
            start = self.buffer.get_iter_at_line(line).iter
            end = start.copy()
            if not end.ends_line():
                end.forward_to_line_end()
            tags = {t.get_property("name") for t in start.get_tags()}
            in_code = next((name for name in tags if name in self.code_blocks), None)
            if code_open and in_code != code_open:
                lines.append(self.code_blocks[code_open][0])
                code_open = None
            if in_code and not code_open:
                marker, info = self.code_blocks[in_code]
                lines.append(marker+info)
                code_open = in_code
            if "literal" in tags or in_code:
                text = self.buffer.get_text(start, end, True)
            else:
                text = self._inline_markdown(start, end)
                for n in range(1,4):
                    if "h"+str(n) in tags:text = "#"*n + " " + text;break
                text = re.sub(r"^(\s*)• ", r"\1- ", text)
                text = re.sub(r"^(\s*)❯ ", r"\1> ", text)
                text = text.replace("- ☑ ", "- [x] ").replace("- ☐ ", "- [ ] ")
            lines.append(text)
        if code_open:lines.append(self.code_blocks[code_open][0])
        return "\n".join(lines)
