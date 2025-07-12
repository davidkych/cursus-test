#!/usr/bin/env python3
"""
lcsd_util_af_master_parser.py
=============================

Helper for scraping LCSD “運動場 / Athletic-Field” pages.

Behaviour (2025-07-06)
----------------------
• **Default** — one JSON record per `<a name="…">` anchor (legacy).  
• **Opt-in split** — if the <設施> block text contains 「主運動場」/「主場」 (or
  any heading that ends with「場」) that anchor is split into *sub-facilities*:

      1060a → 將軍澳運動場主運動場
      1060b → 將軍澳運動場副運動場
      …

New fields & fixes
------------------
1. `400m_loop`  → bool (True ↔ facility list mentions a 400 m track)  
2. `maintenance_days` → list of machine-readable dicts  
   `{"weekday":1-7, "start":"HH:MM"|None, "end":"HH:MM"|None}` – **no
   `section` key**.  When the page lists separate 主場 / 副場 maintenance days,
   each sub-facility only keeps the entries that belong to itself.  
3. **Jogging schedule** — Excel / PDF for the **same month** are now merged
   into a single entry (no more duplicate months).  
4. **Sub-facility extraction** rewritten; handles nested markup so every
   主場 / 副場 gets its own `facilities` list.  
5. Record `name` concatenates without the stray hyphen:  
   `將軍澳運動場主運動場`, `將軍澳運動場副運動場`.

-------------------------------------------------------------------------------
"""

from __future__ import annotations

import copy
import itertools
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag

# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #

_DEFAULT_KEYWORDS: Dict[str, str] = {
    "description": "簡介",
    "facilities": "設施",
    "jogging": "緩步跑開放時間",
    "opening": "開放時間",
    "maintenance": "定期保養日",
}

_SPLIT_TRIGGERS = ("主運動場", "主場")
_SUB_FAC_ORDER = ("主運動場", "副運動場")

_WEEKDAY_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}

_400M_RE = re.compile(r"(400\s*米|400m)", re.I)

# --------------------------------------------------------------------------- #
# Small helpers                                                               #
# --------------------------------------------------------------------------- #


def _parse_time(token: str) -> Optional[str]:
    """Convert ‘上午8時’ / ‘下午5時’ → 24-hour ‘08:00’ / ‘17:00’ strings."""
    m = re.match(r"(上午|下午)?\s*(\d{1,2})時", token)
    if not m:
        return None
    period, hour = m.groups()
    hour = int(hour)
    if period == "下午" and hour != 12:
        hour += 12
    if period == "上午" and hour == 12:
        hour = 0
    return f"{hour:02d}:00"


def _parse_maintenance(sentences: List[str]) -> List[dict]:
    """
    Chinese → structured maintenance descriptors.

    Handles patterns like  
        • ‘逢星期一上午8時至下午5時’  
        • ‘主場 – 逢星期一’ ／ ‘副場 – 逢星期五’
    """
    out: List[dict] = []
    for s in sentences:
        # split multiple clauses joined by ‘、’
        for clause in re.split(r"[、;；]", s.strip(" 。")):
            if not clause:
                continue
            section = None
            if "–" in clause or "-" in clause:
                section, clause = re.split(r"[–-]", clause, 1)
                section = section.strip()

            m_wd = re.search(r"星期([一二三四五六日天])", clause)
            if not m_wd:
                continue
            weekday = _WEEKDAY_MAP[m_wd.group(1)]

            times = re.findall(r"(上午|下午)?\s*\d{1,2}時", clause)
            start = _parse_time(times[0]) if len(times) >= 1 else None
            end   = _parse_time(times[1]) if len(times) >= 2 else None

            out.append(
                {"weekday": weekday, "start": start, "end": end, "section": section}
            )
    return out


def _filter_maintenance(maint: List[dict], head: Optional[str]) -> List[dict]:
    """
    • If `head` is None (non-split facility): keep only entries **without**
      a section tag, drop the field entirely.  
    • For sub-facilities:  
        - 主*: keep section == None **or** contains ‘主’  
        - 副*: keep section == None **or** contains ‘副’
    """
    mode: Optional[str] = None
    if head:
        if "主" in head:
            mode = "主"
        elif "副" in head:
            mode = "副"

    filtered: List[dict] = []
    for m in maint:
        sec = m.get("section")
        keep = False
        if mode is None:              # legacy / unsplit
            keep = sec is None
        else:                         # split
            keep = sec is None or (sec and mode in sec)

        if keep:
            filtered.append(
                {k: v for k, v in m.items() if k != "section"}
            )
    return filtered


def _has_400m_loop(items: List[str]) -> bool:
    """True iff any bullet mentions a 400 m loop / track."""
    return bool(_400M_RE.search(" ".join(items)))


# --------------------------------------------------------------------------- #
# Sub-facility extraction                                                     #
# --------------------------------------------------------------------------- #


def _extract_sub_facilities(fac_div: Tag) -> Dict[str, List[str]]:
    """
    Return mapping {heading → [bullet …]} for blocks like

        主運動場<ul>…</ul><br/>副運動場<ul>…</ul>

    or nested variants.
    """
    sub: Dict[str, List[str]] = {}

    # 1️⃣ primary strategy — locate every <ul>; grab nearest previous sibling
    for ul in fac_div.find_all("ul"):
        prev = ul.previous_sibling
        while prev and (
            isinstance(prev, NavigableString) and not prev.strip()
            or isinstance(prev, Tag) and prev.name == "br"
        ):
            prev = prev.previous_sibling
        if not prev:
            continue
        head_txt = (
            prev.get_text(strip=True) if isinstance(prev, Tag) else prev.strip()
        )
        if head_txt.endswith("場"):
            bullets = [
                li.get_text(strip=True)
                for li in ul.find_all("li") if li.get_text(strip=True)
            ]
            sub.setdefault(head_txt, []).extend(bullets)

    # 2️⃣ fallback — flat scan if nothing captured
    if not sub:
        current = None
        for node in fac_div.children:
            if isinstance(node, NavigableString):
                txt = node.strip()
                if txt.endswith("場"):
                    current = txt
                    sub.setdefault(current, [])
            elif isinstance(node, Tag):
                if node.name == "ul" and current:
                    sub[current].extend(
                        li.get_text(strip=True)
                        for li in node.find_all("li") if li.get_text(strip=True)
                    )
                else:
                    txt = node.get_text(strip=True)
                    if txt.endswith("場"):
                        current = txt
                        sub.setdefault(current, [])

    # deterministic order
    ordered: Dict[str, List[str]] = {}
    for key in _SUB_FAC_ORDER:
        if key in sub:
            ordered[key] = sub.pop(key)
    ordered.update(dict(sorted(sub.items())))
    return ordered


# --------------------------------------------------------------------------- #
# Main public function                                                        #
# --------------------------------------------------------------------------- #


def parse_facilities(
    html: str,
    did: str | int,
    *,
    keywords: Dict[str, str] | None = None,
) -> List[dict]:
    """
    Parse **one** LCSD “運動場” details page. Returns a list of JSON-serialisable
    dicts following the schema described in the docstring.
    """
    kw = {**_DEFAULT_KEYWORDS, **(keywords or {})}
    soup = BeautifulSoup(html, "html.parser")
    out: List[dict] = []

    for anchor in soup.find_all("a", attrs={"name": True}):
        base_num = anchor["name"].strip()

        # ── isolate this anchor’s block ─────────────────────────────────────
        frag_nodes = []
        for sib in anchor.next_siblings:
            if getattr(sib, "name", None) == "a" and sib.has_attr("name"):
                break
            frag_nodes.append(sib)
        block = BeautifulSoup("".join(str(n) for n in frag_nodes), "html.parser")

        title_tag = block.find("h4", class_="details_title")
        if not title_tag:
            continue  # malformed section, skip

        # ── skeleton ────────────────────────────────────────────────────────
        tmpl = {
            "did_number": str(did),
            "lcsd_number": base_num,
            "name": title_tag.get_text(strip=True),
            "address": None,
            "phone": None,
            "fax": None,
            "email": None,
            "description": None,
            "facilities": [],
            "400m_loop": False,
            "opening_hours": None,
            "maintenance_days": [],      # will be filled shortly
            "jogging_schedule": [],
        }

        def _section(k: str) -> Optional[Tag]:
            return block.find("h4", string=lambda t: t and kw[k] in t)

        # ── description ──
        if (h := _section("description")) and (p := h.find_next("p")):
            tmpl["description"] = p.get_text(strip=True) or None

        # ── jogging schedule (merge Excel + PDF pair) ──
        if (h := _section("jogging")):
            table = (
                h.find_next("table", class_="jogging_pdf")
                or h.find_next("div").find("table", class_="jogging_pdf")
            )
            if table:
                rows = table.find_all("tr")
                if len(rows) >= 2:
                    links_row, label_row = rows[0], rows[1]
                    link_cells  = links_row.find_all("td")
                    label_cells = label_row.find_all("td")
                    sched_map: Dict[str, dict] = {}

                    for idx, lbl_td in enumerate(label_cells):
                        label = lbl_td.get_text(strip=True)
                        if not label:
                            continue
                        entry = sched_map.setdefault(
                            label, {"month_year": label, "excel_url": None, "pdf_url": None}
                        )
                        if idx < len(link_cells):
                            for a in link_cells[idx].find_all("a", href=True):
                                href = a["href"].strip()
                                if href.endswith(".xlsx"):
                                    entry["excel_url"] = href
                                elif href.endswith(".pdf"):
                                    entry["pdf_url"] = href
                    tmpl["jogging_schedule"] = list(sched_map.values())

        # ── opening hours ──
        if (h := _section("opening")):
            parts = []
            node = h.next_sibling
            while node and not (getattr(node, "name", None) == "h4"):
                if getattr(node, "name", None) == "div":
                    parts.extend(
                        p.get_text(strip=True)
                        for p in node.find_all("p") if p.get_text(strip=True)
                    )
                node = node.next_sibling
            if parts:
                tmpl["opening_hours"] = " ".join(parts)

        # ── maintenance days (raw, with section tags) ──
        raw_maint: List[dict] = []
        if (h := _section("maintenance")) and (p := h.find_next("p")):
            raw_strings = [
                s.strip() for s in p.get_text("。", strip=True).split("。") if s.strip()
            ]
            raw_maint = _parse_maintenance(raw_strings)
        tmpl["maintenance_days"] = raw_maint  # temp; will be filtered later

        # ── contact table ──
        if (tbl := block.find("table", class_="table table-responsive table-striped")):
            for row in tbl.find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all("td")]
                if len(cells) < 2:
                    continue
                key, val = cells[0], cells[1]
                if "地址" in key:
                    tmpl["address"] = val
                elif key == "電話":
                    tmpl["phone"] = val
                elif key == "傳真":
                    tmpl["fax"] = val
                elif key == "電郵":
                    tmpl["email"] = val

        # ── facilities (split or legacy) ──
        fac_div = (
            _section("facilities")
            and _section("facilities").find_next("div", class_="fac_para")
        )
        emit: List[dict] = []

        if fac_div:
            fac_text = fac_div.get_text()
            do_split = any(t in fac_text for t in _SPLIT_TRIGGERS)

            if do_split:
                sub_map = _extract_sub_facilities(fac_div)
                for idx, (head, bullets) in enumerate(sub_map.items()):
                    rec = copy.deepcopy(tmpl)
                    rec["lcsd_number"] = f"{base_num}{chr(ord('a') + idx)}"
                    rec["name"] = f"{tmpl['name']}{head}"
                    rec["facilities"] = bullets
                    rec["400m_loop"] = _has_400m_loop(bullets)
                    # filter maintenance for this sub-facility & drop `section`
                    rec["maintenance_days"] = _filter_maintenance(raw_maint, head)
                    emit.append(rec)
            else:
                bullets = [
                    li.get_text(strip=True)
                    for li in fac_div.find_all("li") if li.get_text(strip=True)
                ]
                tmpl["facilities"] = bullets
                tmpl["400m_loop"] = _has_400m_loop(bullets)
                # legacy / unsplit facility: keep only section-less entries
                tmpl["maintenance_days"] = _filter_maintenance(raw_maint, None)

        out.extend(emit or [tmpl])

    return out
