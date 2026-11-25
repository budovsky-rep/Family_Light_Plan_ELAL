"""Opaque-box End-to-End (E2E) test suite for family_vacation_planner (Tiers 1-4)."""

from __future__ import annotations

import re
import sys
import types
from html.parser import HTMLParser
from typing import Any

try:
    import bs4 as _bs4  # noqa: F401
except ModuleNotFoundError:
    _VOID_TAGS = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    )
    _SEL_TOKEN_RE = re.compile(r"^([a-zA-Z0-9_-]+)?((?:#[a-zA-Z0-9_-]+|\.[a-zA-Z0-9_-]+)*)$")

    class _StdlibTag:
        def __init__(self, name: str, attrs: dict[str, Any]) -> None:
            self.name = name.lower()
            self.attrs = attrs
            self.children: list[_StdlibTag | str] = []

        def get(self, key: str, default: Any = None) -> Any:
            return self.attrs.get(key, default)

        def __getitem__(self, key: str) -> Any:
            return self.attrs[key]

        def has_attr(self, key: str) -> bool:
            return key in self.attrs

        def _collect_texts(self, out: list[str]) -> None:
            for ch in self.children:
                if isinstance(ch, str):
                    out.append(ch)
                else:
                    ch._collect_texts(out)

        def get_text(self, separator: str = "", strip: bool = False) -> str:
            parts: list[str] = []
            self._collect_texts(parts)
            if strip:
                parts = [p.strip() for p in parts if p.strip()]
            res = separator.join(parts)
            return res.strip() if strip else res

        @property
        def text(self) -> str:
            return self.get_text()

        def _iter_descendants(self):
            for ch in self.children:
                if isinstance(ch, _StdlibTag):
                    yield ch
                    yield from ch._iter_descendants()

        def _matches_filter(self, name: str | None, checks: dict[str, Any]) -> bool:
            if name is not None and self.name != name.lower():
                return False
            for k, expected in checks.items():
                attr_key = "class" if k == "class_" else k
                if expected is True:
                    if attr_key not in self.attrs:
                        return False
                    continue
                if expected is False or expected is None:
                    if attr_key in self.attrs:
                        return False
                    continue
                actual = self.attrs.get(attr_key)
                if attr_key == "class":
                    cls_list = actual if isinstance(actual, list) else str(actual or "").split()
                    if isinstance(expected, str):
                        for req_c in expected.split():
                            if req_c not in cls_list:
                                return False
                    elif expected not in cls_list:
                        return False
                else:
                    if str(actual) != str(expected):
                        return False
            return True

        def find_all(self, name: str | None = None, attrs: dict[str, Any] | None = None, **kwargs: Any) -> list[_StdlibTag]:
            merged: dict[str, Any] = {}
            if attrs:
                merged.update(attrs)
            merged.update(kwargs)
            return [el for el in self._iter_descendants() if el._matches_filter(name, merged)]

        def find(self, name: str | None = None, attrs: dict[str, Any] | None = None, **kwargs: Any) -> _StdlibTag | None:
            matches = self.find_all(name, attrs=attrs, **kwargs)
            return matches[0] if matches else None

        @staticmethod
        def _matches_simple_selector(el: _StdlibTag, token: str) -> bool:
            m = _SEL_TOKEN_RE.match(token)
            if not m:
                return False
            tag_name, qualifiers = m.group(1), m.group(2) or ""
            if tag_name and el.name != tag_name.lower():
                return False
            for qual in re.findall(r"[#.][a-zA-Z0-9_-]+", qualifiers):
                if qual.startswith("#"):
                    if el.attrs.get("id") != qual[1:]:
                        return False
                elif qual.startswith("."):
                    cls_list = el.attrs.get("class") or []
                    if qual[1:] not in cls_list:
                        return False
            return True

        def select(self, selector: str) -> list[_StdlibTag]:
            tokens = [t for t in selector.strip().split() if t]
            if not tokens:
                return []
            current: list[_StdlibTag] = [self]
            for tok in tokens:
                next_matches: list[_StdlibTag] = []
                seen_ids: set[int] = set()
                for root_el in current:
                    for desc in root_el._iter_descendants():
                        if id(desc) not in seen_ids and self._matches_simple_selector(desc, tok):
                            seen_ids.add(id(desc))
                            next_matches.append(desc)
                current = next_matches
            return current

        def select_one(self, selector: str) -> _StdlibTag | None:
            res = self.select(selector)
            return res[0] if res else None

    class _DomBuilder(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.root = _StdlibTag("[document]", {})
            self.stack: list[_StdlibTag] = [self.root]

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            parsed_attrs: dict[str, Any] = {}
            for k, v in attrs:
                if k == "class":
                    parsed_attrs["class"] = (v or "").split()
                else:
                    parsed_attrs[k] = "" if v is None else v
            node = _StdlibTag(tag, parsed_attrs)
            self.stack[-1].children.append(node)
            if tag.lower() not in _VOID_TAGS:
                self.stack.append(node)

        def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            parsed_attrs: dict[str, Any] = {}
            for k, v in attrs:
                if k == "class":
                    parsed_attrs["class"] = (v or "").split()
                else:
                    parsed_attrs[k] = "" if v is None else v
            node = _StdlibTag(tag, parsed_attrs)
            self.stack[-1].children.append(node)

        def handle_endtag(self, tag: str) -> None:
            t_low = tag.lower()
            for idx in range(len(self.stack) - 1, 0, -1):
                if self.stack[idx].name == t_low:
                    del self.stack[idx:]
                    break

        def handle_data(self, data: str) -> None:
            if data:
                self.stack[-1].children.append(data)

    def BeautifulSoup(markup: str, features: str = "html.parser") -> _StdlibTag:  # noqa: N802, ARG001
        parser = _DomBuilder()
        parser.feed(markup)
        parser.close()
        return parser.root

    _shim_mod = types.ModuleType("bs4")
    _shim_mod.BeautifulSoup = BeautifulSoup  # type: ignore[attr-defined]
    sys.modules["bs4"] = _shim_mod
