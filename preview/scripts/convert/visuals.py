"""圖像元件：md 裡幾行短語法，轉成對照、架構、時間軸、數字卡、卡片、步驟、重點框；另含版面體檢。

設計要點（預覽頁不要整頁白底黑字一堆文字，要白話、不重複、盡量圖像化，製作又不能太耗資源）：
- 寫的人只要寫幾行「A｜B｜C」短語法，圖由這支畫，不用每頁手刻 HTML 或 SVG
- 所有文字都留在 DOM 裡，可以框選評論
- 箭頭、編號、圓點一律用 CSS 畫，不輸出特殊符號字元（自帶字型沒有的字會掉回系統字，整頁字型就不一致）
- class 一律 pv- 開頭
- 看不懂的區塊回傳 None，交回原本的流程圖轉換或程式碼區塊，不硬轉
"""
from __future__ import annotations  # 讓 Python 3.9（macOS 內建）也能跑
import html
import re

COMPARE = {'對照', '比較', 'compare'}
LAYERS = {'架構', '架構圖', '分層', 'arch', 'layers'}
TIMELINE = {'時間軸', '時程', 'timeline'}
STATS = {'數字', '數字卡', 'stats'}
CARDS = {'卡片', '選項', '分工', 'cards'}
STEPS = {'步驟', 'steps'}
ALL_LANGS = COMPARE | LAYERS | TIMELINE | STATS | CARDS | STEPS

_SEP = re.compile(r'\s*[｜|]\s*')
_ARROW = re.compile(r'\s*(?:→|->|=>)\s*')
_DONE = re.compile(r'^(?:✅|✔️?|☑️?|\[x\])\s*', re.I)
_NOW = re.compile(r'^(?:👉|▶️?|\[>\])\s*')
_PICK = re.compile(r'^(?:★|⭐️?)\s*')


def _cells(line):
    return [cell for cell in _SEP.split(line.strip())]


def _compare(lines, inline):
    head = _ARROW.split(lines[0].strip(), maxsplit=1)
    if len(head) != 2 or not all(head):
        return None
    rows = []
    for line in lines[1:]:
        label = ''
        text = line.strip()
        parts = _SEP.split(text, maxsplit=1)
        if len(parts) == 2 and _ARROW.search(parts[1]) and not _ARROW.search(parts[0]):
            label, text = parts
        pair = _ARROW.split(text, maxsplit=1)
        if len(pair) != 2 or not all(pair):
            return None
        rows.append((label, pair[0], pair[1]))
    if not rows:
        return None
    labelled = any(label for label, _, _ in rows)
    old, new = (html.escape(value, quote=True) for value in head)
    out = ['<figure class="pv-vis pv-vis--wide pv-compare' + (' pv-compare--labelled' if labelled else '') + '">',
           '<div class="pv-compare-row pv-compare-head">',
           '<div class="pv-compare-label"></div>' if labelled else '',
           '<div class="pv-compare-old">' + inline(head[0]) + '</div>',
           '<div class="pv-compare-new">' + inline(head[1]) + '</div></div>']
    for label, before, after in rows:
        out.append('<div class="pv-compare-row">')
        if labelled:
            out.append('<div class="pv-compare-label">' + inline(label) + '</div>')
        out.append(f'<div class="pv-compare-old" data-label="{old}">' + inline(before) + '</div>')
        out.append(f'<div class="pv-compare-new" data-label="{new}">' + inline(after) + '</div></div>')
    out.append('</figure>')
    return ''.join(out)


def _with_note(text, inline):
    """「名稱（補充）」拆成主文字加小字，括號本身不輸出。"""
    match = re.match(r'^(.*?)\s*[（(]([^（）()]+)[）)]\s*$', text)
    if match and match[1].strip():
        return inline(match[1].strip()) + '<small>' + inline(match[2].strip()) + '</small>'
    return inline(text)


def _node(text, inline):
    return '<div class="pv-node">' + _with_note(text, inline) + '</div>'


def _layers(lines, inline):
    out, tone, count, link = [], 0, 0, None
    for line in lines:
        text = line.strip()
        arrow = re.match(r'^(?:↓|↕|⇣)\s*(.*)$', text)
        if arrow and count:
            link = arrow[1].strip()
            continue
        parts = _SEP.split(text, maxsplit=1)
        if len(parts) != 2 or not all(parts):
            return None
        name, items = parts
        chained = bool(_ARROW.search(items))
        nodes = [item.strip() for item in (_ARROW.split(items) if chained else re.split(r'\s*[、,，]\s*', items)) if item.strip()]
        if not nodes:
            return None
        if count:
            out.append('<div class="pv-layer-link">' + (inline(link) if link else '') + '</div>')
        link = None
        tone = tone % 4 + 1
        count += 1
        out.append(f'<div class="pv-layer" data-tone="{tone}"><div class="pv-layer-name">' + _with_note(name, inline) + '</div>'
                   '<div class="pv-layer-items' + (' pv-layer-items--chain' if chained else '') + '">' +
                   ''.join(_node(node, inline) for node in nodes) + '</div></div>')
    if count < 2:
        return None
    return '<figure class="pv-vis pv-vis--wide pv-layers">' + ''.join(out) + '</figure>'


def _timeline(lines, inline):
    items = []
    for line in lines:
        text, state = line.strip(), ''
        if _DONE.match(text):
            text, state = _DONE.sub('', text), 'done'
        elif _NOW.match(text):
            text, state = _NOW.sub('', text), 'now'
        cells = _cells(text)
        if len(cells) < 2 or not cells[0] or not cells[1]:
            return None
        items.append((state, cells))
    if len(items) < 2:
        return None
    staged = any(state for state, _ in items)
    out = ['<figure class="pv-vis pv-timeline">']
    for state, cells in items:
        state = state or ('todo' if staged else 'plain')
        out.append(f'<div class="pv-tl-item" data-state="{state}"><div class="pv-tl-time">' + inline(cells[0]) + '</div>'
                   '<div class="pv-tl-body"><div class="pv-tl-title">' + inline(cells[1]) + '</div>' +
                   ''.join('<div class="pv-tl-desc">' + inline(cell) + '</div>' for cell in cells[2:] if cell) + '</div></div>')
    out.append('</figure>')
    return ''.join(out)


def _stats(lines, inline):
    tiles = []
    for line in lines:
        cells = _cells(line)
        if len(cells) < 2 or not cells[0] or not cells[1]:
            return None
        number = re.match(r'^(\S+)\s+(.+)$', cells[0])
        big = inline(number[1]) + '<small>' + inline(number[2]) + '</small>' if number else inline(cells[0])
        tiles.append('<div class="pv-stat"><div class="pv-stat-num">' + big + '</div><div class="pv-stat-label">' + inline(cells[1]) + '</div>' +
                     ''.join('<div class="pv-stat-note">' + inline(cell) + '</div>' for cell in cells[2:] if cell) + '</div>')
    wide = ' pv-vis--wide' if len(tiles) >= 4 else ''
    # 欄數照張數配，最後一排自動撐滿，不會剩一張孤零零掛在左邊留一塊空白（5 張排 3 加 2、7 張排 4 加 3）
    cols = len(tiles) if len(tiles) <= 4 else 3 if len(tiles) in (5, 6, 9) else 4
    return f'<figure class="pv-vis{wide} pv-stats" style="--pv-cols:{cols}">' + ''.join(tiles) + '</figure>'


def _cards(lines, inline):
    cards = []
    for line in lines:
        text = line.strip()
        pick = bool(_PICK.match(text))
        cells = _cells(_PICK.sub('', text))
        if not cells[0]:
            return None
        cards.append('<div class="pv-card' + (' pv-card--pick' if pick else '') + '">' +
                     ('<div class="pv-card-tag">建議</div>' if pick else '') +
                     '<div class="pv-card-title">' + inline(cells[0]) + '</div>' +
                     ''.join('<div class="pv-card-line">' + inline(cell) + '</div>' for cell in cells[1:] if cell) + '</div>')
    if len(cards) < 2:
        return None
    wide = ' pv-vis--wide' if len(cards) >= 3 else ''
    cols = 2 if len(cards) in (2, 4) else 3   # 4 張排 2 乘 2，其餘三欄，最後一排自動撐滿
    return f'<figure class="pv-vis{wide} pv-cards" style="--pv-cols:{cols}">' + ''.join(cards) + '</figure>'


def _steps(lines, inline):
    steps = []
    for line in lines:
        cells = _cells(re.sub(r'^\d+[.、)]\s*', '', line.strip()))
        if not cells[0]:
            return None
        steps.append('<div class="pv-step"><div class="pv-step-title">' + inline(cells[0]) + '</div>' +
                     ''.join('<div class="pv-step-desc">' + inline(cell) + '</div>' for cell in cells[1:] if cell) + '</div>')
    if len(steps) < 2:
        return None
    across = len(steps) <= 4
    names = 'pv-vis pv-steps' + (' pv-steps--across' if across else '') + (' pv-vis--wide' if len(steps) == 4 else '')
    return f'<figure class="{names}" style="--pv-steps:{len(steps)}">' + ''.join(steps) + '</figure>'


def convert_block(lang, lines, inline=None):
    """圍欄區塊的語言標記是圖像元件名稱時轉成元件；語法不完整回傳 None。"""
    inline = inline or (lambda value: html.escape(value, quote=False))
    lines = [line for line in lines if line.strip()]
    if not lines or lang not in ALL_LANGS:
        return None
    for names, render in ((COMPARE, _compare), (LAYERS, _layers), (TIMELINE, _timeline),
                          (STATS, _stats), (CARDS, _cards), (STEPS, _steps)):
        if lang in names:
            return render(lines, inline)
    return None


# 重點框：> [!結論] 可選標題
_CALLOUT_KINDS = (
    ('blue', ('結論', '重點', '一句話', '摘要')),
    ('decide', ('決定', '拍板', '要你決定', '待你決定', '待拍板', '要你做', '你要做的')),
    ('amber', ('注意', '提醒', '小心', '待確認')),
    ('red', ('風險', '危險', '禁止', '警告', '不能做')),
    ('green', ('完成', '好消息', '已解決', '通過')),
    ('gray', ('說明', '白話', '比喻', '補充', '背景', '舉例')),
)
CALLOUT_HEAD = re.compile(r'^\[!([^\]\n]{1,12})\]\s*(.*)$')


def callout_kind(word):
    for kind, words in _CALLOUT_KINDS:
        if word in words:
            return kind
    return 'gray'


def render_callout(word, title, body_html):
    kind = callout_kind(word)
    return (f'<div class="pv-callout pv-callout--{kind}"><div class="pv-callout-head">'
            f'<span class="pv-callout-tag">{html.escape(word, quote=False)}</span>' +
            (f'<span class="pv-callout-title">{title}</span>' if title else '') +
            f'</div><div class="pv-callout-body">{body_html}</div></div>')


# 行內：狀態色標 {綠:已完成}、重點標記 ==文字==
_PILL_TONES = {'綠': 'green', '紅': 'red', '黃': 'amber', '藍': 'blue', '灰': 'gray'}
_PILL = re.compile(r'\{(綠|紅|黃|藍|灰)[:：]([^{}\n]{1,24})\}')
_MARK = re.compile(r'==([^=\n]+)==')


def inline_extras(text):
    """在已經跳脫過的行內文字上加色標與重點標記（行內程式碼已先被抽走，不會誤傷）。"""
    text = _PILL.sub(lambda m: f'<span class="pv-pill pv-pill--{_PILL_TONES[m[1]]}">{m[2].strip()}</span>', text)
    return _MARK.sub(r'<mark class="pv-mark">\1</mark>', text)


# 版面體檢：只提醒不擋。數得出來的才檢查，品味問題留給人看。
_FILLER = ('換句話說', '也就是說', '總結來說', '總而言之', '綜上所述', '簡單來說', '簡而言之', '如前所述',
           '如上所述', '值得注意的是', '需要注意的是', '值得一提的是', '不言而喻', '眾所周知')


def _norm(sentence):
    return re.sub(r'[\s\W_]+', '', sentence)


def _bigrams(value):
    return {value[i:i + 2] for i in range(len(value) - 1)}


def lint(md):
    """回傳提醒清單（字串）。解說型頁面用；合約、完稿這類原文審稿頁請加 --no-lint。"""
    warnings = []
    sections = []          # [標題, 純文字字數, 圖像元件數]
    current = ['（開頭）', 0, 0]
    sentences = []         # (所在段落, 原句, 正規化)
    long_paragraphs = 0
    code_spans = 0
    has_lead_callout = False
    seen_h2 = False
    in_fence = False
    fence_visual = False
    table_open = False
    for raw in md.split('\n'):
        line = raw.rstrip()
        fence = re.match(r'^```(\w*)', line)
        if fence:
            if not in_fence:
                in_fence, fence_visual = True, (fence[1] in ALL_LANGS or fence[1] in ('', 'text', 'txt', 'flow', 'mermaid'))
                if fence_visual:
                    current[2] += 1
            else:
                in_fence = False
            continue
        if in_fence:
            continue
        heading = re.match(r'^(#{1,6})\s+(.*)$', line)
        if heading:
            table_open = False
            if len(heading[1]) == 2:
                sections.append(current)
                current = [heading[2].strip(), 0, 0]
                seen_h2 = True
            continue
        if line.startswith('|'):
            if not table_open:
                current[2] += 1
                table_open = True
            continue
        table_open = False
        if not line.strip():
            continue
        if line.startswith('>'):
            body = line.lstrip('>').strip()
            if CALLOUT_HEAD.match(body):
                current[2] += 1
                if not seen_h2 or len(sections) <= 1:
                    has_lead_callout = True
            continue
        if re.match(r'^!\[[^\]]*\]\([^)]+\)\s*$', line.strip()):
            current[2] += 1
            continue
        if re.match(r'^\s*[-*]\s+\[( |x|X)\]\s+', line):
            continue
        text = re.sub(r'^\s*(?:[-*]|\d+\.)\s+', '', line)
        code_spans += len(re.findall(r'`[^`]+`', text))
        plain = re.sub(r'`[^`]+`|\*\*|~~|==|\{[綠紅黃藍灰][:：]|\}|!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
        current[1] += len(plain)
        if len(plain) > 120:
            long_paragraphs += 1
        for sentence in re.split(r'[。！？!?；;]', plain):
            key = _norm(sentence)
            if len(key) >= 10:
                sentences.append((current[0], sentence.strip(), key))
    sections.append(current)

    total = sum(section[1] for section in sections)
    visuals = sum(section[2] for section in sections)
    if total >= 300 and not has_lead_callout:
        warnings.append('開頭沒有結論框：第一屏先用「> [!結論]」講完整件事，再往下展開')
    for title, chars, count in sections:
        if chars >= 350 and count == 0:
            warnings.append(f'「{title}」這段 {chars} 字全是文字：挑一個圖像元件（對照、架構、時間軸、步驟、卡片、表格）取代大部分敘述')
    if total >= 600 and visuals * 450 < total:
        warnings.append(f'全頁 {total} 字只有 {visuals} 個圖像元件：平均每 450 字至少要有一個')
    if long_paragraphs:
        warnings.append(f'有 {long_paragraphs} 段超過 120 字：拆成短句、清單或元件，一段只講一件事')
    fillers = [word for word in _FILLER if word in md]
    if fillers:
        warnings.append('出現繞圈詞「' + '、'.join(fillers) + '」：後面那句通常是重講一次，整句刪掉')
    if '\u2014\u2014' in md:  # 兩個長破折號
        warnings.append('出現破折號（兩個長破折號連用）：建議不用，改成逗號或拆句')
    if code_spans >= 8:
        warnings.append(f'內文有 {code_spans} 處檔名或程式碼字樣：白話頁寫「它做什麼事」，檔名只留在要照抄的指令裡')
    repeats = []
    for i, (place_a, text_a, key_a) in enumerate(sentences):
        grams_a = _bigrams(key_a)
        for place_b, text_b, key_b in sentences[i + 1:]:
            grams_b = _bigrams(key_b)
            overlap = len(grams_a & grams_b) / max(1, min(len(grams_a), len(grams_b)))
            if overlap >= 0.75:
                repeats.append((place_a, text_a, place_b, text_b))
                break
    for place_a, text_a, place_b, text_b in repeats[:4]:
        warnings.append(f'同一件事講了兩次：「{text_a[:28]}」（{place_a}）和「{text_b[:28]}」（{place_b}），留一處就好')
    if len(repeats) > 4:
        warnings.append(f'另外還有 {len(repeats) - 4} 組重複句')
    return warnings
