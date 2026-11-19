"""深藍暖米殼：預覽頁的外殼與新元件。

md-to-preview.py 用這一份組頁：
樣式 shell-navy.css、互動 runtime.js、底部進度列、浮動目錄、首屏與題目卡的 HTML 都從這裡出，頁面不要自己手抄。
評論系統不在這裡，一律由 inject.py 注入框選評論介面。"""
from __future__ import annotations  # 讓 Python 3.9（macOS 內建）也能跑
import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parents[1] / 'assets'   # 技能資料夾裡的 assets/（本檔在 scripts/convert/ 底下）
# 舊元件（對照、步驟、數字、卡片、表格、重點框、流程卡片）的樣式照載，顏色靠 shell-navy.css 的同名變數換掉
LEGACY_CSS = (ASSETS / 'preview-tokens.css', HERE / 'components.css', HERE / 'visuals.css')


def esc(text):
    return html.escape(text or '', quote=True)


def wbr(text):
    """標題在標點後面補斷行點，配合 word-break:keep-all，不把詞從中間拆開。"""
    return re.sub(r'([，、：；。！？｜＋）」])(?=.)', r'\1<wbr>', esc(text))


def hero(h1, tags=(), lead='', asks='', due='', compact=False):
    """首屏。h1、lead、asks、due 都是已經轉好的 HTML；tags 是純文字。"""
    tag_html = ''.join(f'<span class="pv-badge">{esc(t)}</span>' for t in tags if t)
    return (f'<header class="pv-hero{" is-compact" if compact else ""}">'
            + (f'<div class="pv-badges">{tag_html}</div>' if tag_html else '')
            + f'<h1>{h1}</h1>' + lead
            + (f'<div class="pv-asks">{asks}</div>' if asks else '')
            + (f'<p class="pv-due">{due}</p>' if due else '')
            + '</header>')


def ask(num, label, href=''):
    inner = f'<b>{esc(num)}</b><span>{label}</span>'
    return f'<a class="pv-ask" href="{esc(href)}">{inner}</a>' if href else f'<div class="pv-ask">{inner}</div>'


def question_card(qid, badge, title, kind, options, hint='', check_all=''):
    """題目卡。options 每項：label（純文字，會成為匯出的答案）、note（已轉好的 HTML）、chip、rec、none。
    用 checkbox 模擬單選，單選題才能再點一次取消；互斥與全選由 runtime.js 處理。"""
    kind = 'many' if kind == 'many' else 'one'
    rows = []
    for o in options:
        chip = f'<span class="pv-chip">{esc(o["chip"])}</span> ' if o.get('chip') else ''
        small = f'<small>{chip}{o["note"]}</small>' if o.get('note') or chip else ''
        rec = '<span class="pv-rec">建議</span>' if o.get('rec') else ''
        rows.append(f'<li><label class="pv-opt"><input type="checkbox" data-opt{" data-x" if o.get("none") else ""} value="{esc(o["label"])}">'
                    f'<span><span class="pv-opt-t">{esc(o["label"])}</span>{rec}{small}</span></label></li>')
    full = f'{badge}｜{title}'
    return (f'<div class="pv-q" id="{esc(qid)}" data-q="{esc(qid)}" data-kind="{kind}" data-title="{esc(full)}">'
            f'<div class="pv-q-top"><span class="pv-q-n">{esc(badge)}</span><span class="pv-q-kind">{"選一個" if kind == "one" else "可以選好幾個"}</span><span class="pv-q-state"></span></div>'
            f'<h3>{wbr(title)}</h3>' + (f'<p class="pv-hint">{hint}</p>' if hint else '')
            + f'<ul class="pv-opts">{"".join(rows)}</ul>'
            + (f'<button type="button" class="pv-mini" data-checkall>{esc(check_all)}</button>' if check_all else '') + '</div>')


def section(sid, number, label, headline, body, eyebrow=None):
    """一段：小眉標（預設是編號加段名）、結論式標題、內容。data-n 與 data-label 給浮動目錄用，number 留空時目錄自己照順序編。"""
    shown = eyebrow if eyebrow is not None else f'{number}　{label}'
    return (f'<section class="pv-sec" id="{esc(sid)}" data-n="{esc(number)}" data-label="{esc(label)}">'
            f'<div class="pv-eyebrow">{esc(shown)}</div><h2>{headline}</h2>{body}</section>')


BAR = ('<div class="pv-bar"><div class="pv-bar-in"><div class="pv-bar-txt"><span class="pv-bar-count"></span><div class="pv-meter"><i></i></div></div>'
       '<button type="button" class="pv-next" data-next>下一件</button><button type="button" class="pv-copy" data-copy>複製結果</button></div></div>\n'
       '<div class="pv-toast" role="status"></div>\n'
       '<div class="pv-fallback"><p style="margin:0 0 8px;font-size:14px">自動複製沒成功，請全選下面的文字自己複製。'
       '<button type="button" data-close-fallback style="float:right">關閉</button></p><textarea readonly></textarea></div>')


def page(title, key, main, *, round_no=1, legacy=True, system_fonts=True, wide=False, scripts=''):
    """組出整頁。scripts 是要排在互動程式之前的額外 script（例如標題斷詞），評論 overlay 之後再由 inject 加在最後。"""
    css = ''
    if legacy:
        css = '\n'.join(p.read_text(encoding='utf-8') for p in LEGACY_CSS) + '\n'
    css += (HERE / 'shell-navy.css').read_text(encoding='utf-8')
    js = (HERE / 'runtime.js').read_text(encoding='utf-8')
    return f'''<!DOCTYPE html>
<html lang="zh-Hant" class="{'pv-sysfont' if system_fonts else 'pv-webfont'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{esc(title)}</title><style>{css}</style></head>
<body class="pv-navy{' pv-wide' if wide else ''}" data-pv-key="{esc(key)}" data-pv-title="{esc(title)}" data-pv-round="{int(round_no)}">
<main id="doc">
{main}
</main>
{BAR}
{scripts}
<script>
{js}
</script>
</body></html>'''
