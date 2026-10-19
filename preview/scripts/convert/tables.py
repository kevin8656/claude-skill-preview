"""產生桌機表格與手機卡片共用的 HTML。"""
from __future__ import annotations  # 讓 Python 3.9（macOS 內建）也能跑

import html
import re
from html.parser import HTMLParser


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == 'br':
            self.parts.append(' ')


def _plain(value):
    """保留可讀文字，移除表頭的行內 Markdown 與 HTML 標籤。"""
    value = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', value)
    value = re.sub(r'(`+)(.*?)\1', r'\2', value)
    for marker in ('**', '__', '~~', '*', '_'):
        value = re.sub(re.escape(marker) + r'(.+?)' + re.escape(marker), r'\1', value)
    parser = _Text()
    parser.feed(value)
    parser.close()
    return ''.join(parser.parts).strip()


_BR = re.compile(r'&lt;br\s*/?&gt;', re.I)

# 對照型表格：表頭同時有「舊」與「新」兩種字樣時，舊欄轉灰、新欄淡綠（對照頁要一眼看出哪邊是改完的）
_OLD = re.compile(r'^(?:現在|現況|目前|原本|原來|舊|改前|之前|before)', re.I)
_NEW = re.compile(r'^(?:改完後|改後|改成|新(?!增)|之後|以後|調整後|建議|after)', re.I)


_NUMERIC_CELL = re.compile(r'^[+-]?[\d,]+(?:\.\d+)?\s*[%％元筆條組張天個]?$')


def _numeric_column(cells: list[str]) -> bool:
    """整欄非空格都是數值時為真（空格忽略），用來讓金額欄不折行。"""
    values = [_plain(cell).strip() for cell in cells]
    filled = [value for value in values if value]
    return bool(filled) and all(_NUMERIC_CELL.match(value) for value in filled)


def render_table(head: list[str], rows: list[list[str]], inline) -> str:
    """每列使用同一份文字，手機小標由 data-label 偽元素呈現。

    三個外觀用 class：
    - pv-nowrap：整欄最長 6 字以內（例如「#」「批」「立即」），桌機不折行、不吃最小欄寬，避免短欄被撐寬或擠成兩行。
    - pv-short：16 字以內的儲存格，手機卡片把小標跟值排在同一行，卡片不會每格佔兩行。
    - pv-card-title：第一欄最長 20 字以內時，第一格當手機卡片標題（粗體、不顯示小標）；長句不當標題。
    另外把儲存格裡字面的 <br>（md 表格常用來換行）轉回真正換行。
    """
    labels = [_plain(cell) for cell in head]
    normalized = [(list(row) + [''] * len(head))[:len(head)] for row in rows]
    wide = len(head) >= 4 or any(
        len(_plain(cell)) > 40 for row in [head] + normalized for cell in row
    )
    lengths = [[len(_plain(row[i])) for row in normalized] for i in range(len(head))]
    narrow = [max([len(labels[i])] + lengths[i]) <= 6 for i in range(len(head))]
    # 整欄都是數值（金額、筆數、百分比）時也不折行："115,270" 被拆成兩行會讀錯位數。
    narrow = [narrow[i] or _numeric_column([row[i] for row in normalized]) for i in range(len(head))]
    title_col = bool(head) and max(lengths[0], default=0) <= 20
    tone = ['pv-col-old' if _OLD.match(label) else 'pv-col-new' if _NEW.match(label) else '' for label in labels]
    if not ('pv-col-old' in tone and 'pv-col-new' in tone):
        tone = [''] * len(head)
    classes = 'pv-table-wrap' + (' pv-table-wrap--wide' if wide else '')
    output = [f'<div class="{classes}"><table class="pv-table"><thead><tr>']
    for i, cell in enumerate(head):
        names = ' '.join(name for name in ('pv-nowrap' if narrow[i] else '', tone[i]) if name)
        output.append(f'<th scope="col"' + (f' class="{names}"' if names else '') + f'>{inline(cell)}</th>')
    output.append('</tr></thead><tbody>')
    for row in normalized:
        output.append('<tr>')
        for i, (label, cell) in enumerate(zip(labels, row)):
            attribute = f' data-label="{html.escape(label, quote=True)}"' if label else ''
            size = len(_plain(cell))
            names = []
            if narrow[i]:
                names.append('pv-nowrap')
            if size and size <= 16:
                names.append('pv-short')
            if i == 0 and title_col and size:
                names.append('pv-card-title')
            if tone[i]:
                names.append(tone[i])
            if names:
                attribute += f' class="{" ".join(names)}"'
            output.append(f'<td{attribute}>{_BR.sub("<br>", inline(cell))}</td>')
        output.append('</tr>')
    output.append('</tbody></table></div>')
    return ''.join(output)
