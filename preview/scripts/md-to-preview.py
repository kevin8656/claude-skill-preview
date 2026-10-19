#!/usr/bin/env python3
"""預覽頁產生器：把 Markdown 轉成「可框選評論、可勾選」的 HTML 預覽頁。

用法：
  python3 md-to-preview.py <來源.md> <輸出.html> [--identities "我,訪客"] [--badges "a,b"] [--key storageKey] [--title 標題]
  共用選項：--no-overlay（不含評論功能的乾淨版）、--fonts copy|link|none、--fold "3,4"、--no-lint、--icon

設計要點：
- 樣式全部讀檔內嵌：preview-fonts.css、preview-tokens.css、components.css、visuals.css、shell.css
- 自帶字型（Noto Sans TC、Geist、Geist Mono，皆為 SIL OFL 授權），copy 模式把 woff2 放在輸出檔旁的 preview-fonts/
- 左側可收合目錄；標題在標點與詞之間補斷行點
- ASCII／mermaid 流程圖轉流程卡片、表格在手機變卡片（convert/ 資料夾）
- 圖像元件：```對照／架構／時間軸／數字／卡片／步驟 短語法、> [!結論] 重點框、{綠:文字} 色標、==重點==，
  由 convert/visuals.py 轉換；產頁時印「版面體檢」提醒，--no-lint 關閉
- 自動注入框選評論介面，評論範圍固定在 #doc
- 只用 Python 標準函式庫，不需要另外安裝套件
"""
from __future__ import annotations  # 讓 Python 3.9（macOS 內建）也能跑
import argparse
import hashlib
import json
import html
import os
import re
import sys
import importlib.util
from pathlib import Path

_components = Path(__file__).resolve().parent / 'convert'
def _load_component(name):
    spec = importlib.util.spec_from_file_location('preview_' + name, _components / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

flow = _load_component('flow')
tables = _load_component('tables')
visuals = _load_component('visuals')

injector = _load_component('inject')


def esc(t):
    return html.escape(t, quote=False)


def inline(t):
    """行內語法。順序重要：先抽出行內程式碼，最後再放回，避免內容被其他規則污染。"""
    stash = []

    def keep(m):
        stash.append(m.group(1))
        return f'\x00{len(stash) - 1}\x00'

    t = re.sub(r'`([^`]+)`', keep, t)
    t = esc(t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'~~([^~]+)~~', r'<del>\1</del>', t)
    t = re.sub(r'(?<![*\w])\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', t)
    # 圖片要在連結之前處理，否則 ![說明](路徑) 會變成「!」加一個連結
    t = re.sub(r'!\[([^\]]*)\]\(([^)\s]+)\)',
               r'<img src="\2" alt="\1" loading="lazy">', t)
    t = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)',
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    # 裸網址（前後有空白的那種）
    t = re.sub(r'(?<![">=\w])(https?://[^\s<）】]+)',
               r'<a href="\1" target="_blank" rel="noopener">\1</a>', t)
    t = visuals.inline_extras(t)
    for i, code in enumerate(stash):
        t = t.replace(f'\x00{i}\x00', f'<code>{esc(code)}</code>')
    return t


def slug(text, used):
    s = re.sub(r'[^\w一-鿿]+', '-', text).strip('-').lower() or 'h'
    n, base = 1, s
    while s in used:
        n += 1
        s = f'{base}-{n}'
    used.add(s)
    return s


def convert(md, fold=()):
    """fold：要摺疊的標題層級集合（例如 {3, 4}），該層標題與其內容包成 <details>。"""
    lines = md.split('\n')
    out, toc = [], []
    used = set()
    i, n = 0, len(lines)

    def close_list(stack):
        while stack:
            out.append(f'</{stack.pop()}>')

    list_stack = []
    last_heading = ''
    check_ids = {}
    fold_stack = []

    def close_folds(level):
        while fold_stack and fold_stack[-1] >= level:
            fold_stack.pop()
            out.append('</div></details>')

    def list_item(text):
        task = re.match(r'^\[( |x|X)\]\s+(.*)$', text)
        if not task:
            return f'<li>{inline(text)}</li>'
        # 勾選方框：在頁面上直接勾選，勾選結果跟評論一起複製
        # id 用「所在標題＋文字」算，段落順序調整也不會對錯題；同段同字再加序號
        base = hashlib.md5(f'{last_heading}|{task.group(2).strip()}'.encode('utf-8')).hexdigest()[:10]
        seen = check_ids.get(base, 0)   # 🚨 不能叫 n：迴圈外層的 n 是總行數，蓋掉會讓轉換提早結束
        check_ids[base] = seen + 1
        cid = base if seen == 0 else f'{base}-{seen}'
        checked = ' checked' if task.group(1).lower() == 'x' else ''
        return (f'<li class="pv-check"><label><input type="checkbox" data-pv-check="{cid}"{checked}>'
                f'<span>{inline(task.group(2))}</span></label></li>')

    def callout_body(rows):
        # 重點框裡可以放短段落、清單與勾選方框
        parts, items, para = [], [], []

        def flush():
            if para:
                parts.append('<p>' + '<br>'.join(inline(row) for row in para) + '</p>')
                para.clear()
            if items:
                parts.append('<ul>' + ''.join(items) + '</ul>')
                items.clear()

        for row in rows:
            item = re.match(r'^(?:[-*]|\d+\.)\s+(.*)$', row)
            if item:
                if para:
                    flush()
                items.append(list_item(item.group(1)))
            elif not row:
                flush()
            else:
                if items:
                    flush()
                para.append(row)
        flush()
        return ''.join(parts)

    while i < n:
        ln = lines[i]

        # 程式碼區塊：整段原樣，不做任何 markdown 處理
        m = re.match(r'^```(\w*)', ln)
        if m:
            close_list(list_stack)
            lang = m.group(1)
            i += 1
            buf = []
            while i < n and not lines[i].startswith('```'):
                buf.append(lines[i])
                i += 1
            i += 1
            converted = visuals.convert_block(lang, buf, inline) or flow.convert_block(lang, buf, inline)
            out.append(converted if converted is not None else
                       f'<pre class="code" data-lang="{esc(lang)}"><code>'
                       f'{esc(chr(10).join(buf))}</code></pre>')
            continue

        # 表格
        if ln.startswith('|') and i + 1 < n and re.match(r'^\|[\s:\-|]+\|?\s*$', lines[i + 1]):
            close_list(list_stack)
            head = [c.strip() for c in ln.strip().strip('|').split('|')]
            i += 2
            rows = []
            while i < n and lines[i].startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            out.append(tables.render_table(head, rows, inline))
            continue

        # 標題
        m = re.match(r'^(#{1,6})\s+(.*)$', ln)
        if m:
            close_list(list_stack)
            lv = len(m.group(1))
            txt = m.group(2).strip()
            sid = slug(txt, used)
            if lv <= 3:
                toc.append((lv, txt, sid))
                last_heading = txt
            close_folds(lv)
            heading = f'<h{lv} id="{sid}">{inline(txt)}</h{lv}>'
            if lv in fold:
                out.append(f'<details class="pv-fold"><summary>{heading}</summary><div class="pv-fold-body">')
                fold_stack.append(lv)
            else:
                out.append(heading)
            i += 1
            continue

        # 水平線
        if re.match(r'^(-{3,}|\*{3,}|_{3,})\s*$', ln):
            close_list(list_stack)
            out.append('<hr>')
            i += 1
            continue

        # 引用
        if ln.startswith('>'):
            close_list(list_stack)
            buf = []
            while i < n and lines[i].startswith('>'):
                buf.append(lines[i].lstrip('>').strip())
                i += 1
            callout = visuals.CALLOUT_HEAD.match(buf[0])
            if callout:
                out.append(visuals.render_callout(callout.group(1).strip(), inline(callout.group(2).strip()), callout_body(buf[1:])))
                continue
            out.append('<blockquote>' + '<br>'.join(inline(b) for b in buf) + '</blockquote>')
            continue

        # 清單（支援兩層縮排）
        m = re.match(r'^(\s*)([-*]|\d+\.)\s+(.*)$', ln)
        if m:
            indent = len(m.group(1))
            tag = 'ol' if re.match(r'\d', m.group(2)) else 'ul'
            depth = 1 if indent < 2 else 2
            while len(list_stack) > depth:
                out.append(f'</{list_stack.pop()}>')
            if len(list_stack) < depth:
                out.append(f'<{tag}>')
                list_stack.append(tag)
            out.append(list_item(m.group(3)))
            i += 1
            continue

        # 空行
        if not ln.strip():
            close_list(list_stack)
            i += 1
            continue

        # 段落
        close_list(list_stack)
        buf = [ln]
        i += 1
        while i < n and lines[i].strip() and not re.match(
                r'^(#{1,6}\s|```|\||>|\s*([-*]|\d+\.)\s|(-{3,}|\*{3,}|_{3,})\s*$)', lines[i]):
            buf.append(lines[i])
            i += 1
        text = " ".join(b.strip() for b in buf)
        only_img = re.fullmatch(r'!\[([^\]]*)\]\(([^)\s]+)\)', text)
        if only_img:
            # 獨立一段的圖片變 figure，圖說用 alt（alt 不是文字節點，不會跟圖說重複干擾評論錨定）
            cap = only_img.group(1)
            out.append(f'<figure class="pv-figure">{inline(text)}'
                       + (f'<figcaption>{esc(cap)}</figcaption>' if cap else '') + '</figure>')
        else:
            out.append(f'<p>{inline(text)}</p>')

    close_list(list_stack)
    close_folds(1)
    return '\n'.join(out), toc


def plain(value):
    return html.unescape(re.sub(r'<[^>]+>', '', value))


def heading_breaks(value):
    """只在文字節點加斷行點，標籤屬性與既有行內格式保持完整。"""
    return ''.join(part if part.startswith('<') else re.sub(r'([，、：；！？）」』])', r'\1<wbr>', part)
                   for part in re.split(r'(<[^>]+>)', value))


def rebuild_headings(body):
    used, toc = set(), []
    def replace(match):
        level, attrs, text = match.groups()
        text = re.sub(r'<wbr\s*/?>', '', text, flags=re.I)
        label = plain(text)
        sid = slug(label, used)
        attrs = re.sub(r'\s+id\s*=\s*(?:"[^"]*"|\x27[^\x27]*\x27|[^\s>]+)', '', attrs, flags=re.I)
        if int(level) in (2, 3):
            toc.append((int(level), label, sid))
        return f'<h{level}{attrs} id="{html.escape(sid, quote=True)}">{heading_breaks(text)}</h{level}>'
    return re.sub(r'<h([1-6])\b([^>]*)>(.*?)</h\1\s*>', replace, body, flags=re.S | re.I), toc


# 標題斷詞：keep-all 只會在標點與空白斷行，遇到沒有標點的長串會整串搬到下一行，第一行只剩幾個字。
# 用瀏覽器內建 Intl.Segmenter 斷詞，只在「兩邊都是兩字以上的詞」之間補 <wbr>：
# 常見詞（架構｜部署、路徑｜截斷）可以斷，罕見詞被拆成單字的（塔｜羅、接｜案｜班）不會被斷開。
# 必須在評論 overlay 建文字索引之前同步執行（放在 overlay 前面）；<wbr> 不增加文字，錨定不受影響。
HEADING_SCRIPT = r"""<script>
(() => {
  if (!(window.Intl && Intl.Segmenter)) return;
  const seg = new Intl.Segmenter('zh-Hant', { granularity: 'word' });
  const cjk = /[㐀-鿿豈-﫿]/;  // 中日韓統一漢字與相容區（字元直貼）
  document.querySelectorAll('#doc h1, #doc h2, #doc h3').forEach(h => {
    const walker = document.createTreeWalker(h, NodeFilter.SHOW_TEXT, {
      acceptNode: n => n.parentElement && n.parentElement.closest('code') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const parts = [...seg.segment(node.nodeValue)].map(x => x.segment);
      if (parts.length < 2) return;
      const frag = document.createDocumentFragment();
      let buf = '', inserted = false;
      // 從 i+1 起到下一個標點或空白為止，還剩幾個中文字；剩 3 字以內就不斷，避免行尾只掉兩個字（「永久／遺失」）
      const rest = i => { let n = 0; for (let k = i; k < parts.length && cjk.test(parts[k]); k++) n += parts[k].length; return n; };
      parts.forEach((part, i) => {
        buf += part;
        const next = parts[i + 1];
        if (next && part.length >= 2 && next.length >= 2 && cjk.test(part) && cjk.test(next) && rest(i + 1) > 3) {
          frag.append(buf, document.createElement('wbr'));
          buf = ''; inserted = true;
        }
      });
      if (!inserted) return;
      frag.append(buf);
      node.replaceWith(frag);
    });
  });
})();
</script>"""


TOC_SCRIPT = r"""<script>
(() => {
  const key = __TOC_KEY__;
  const body = document.body;
  const toc = document.querySelector('.pv-toc');
  const open = document.querySelector('.pv-toc-open');
  const close = toc.querySelector('button');
  const desktop = matchMedia('(min-width:1100px)');
  let collapsed = false;
  try { collapsed = localStorage.getItem(key) === 'closed'; } catch (_) {}
  function render() {
    body.classList.toggle('pv-toc-closed', collapsed);
    const expanded = desktop.matches ? !collapsed : body.classList.contains('pv-toc-mobile-open');
    open.setAttribute('aria-expanded', String(expanded));
  }
  function toggle(value) {
    if (desktop.matches) {
      collapsed = !value;
      try { localStorage.setItem(key, collapsed ? 'closed' : 'open'); } catch (_) {}
    } else { body.classList.toggle('pv-toc-mobile-open', value); }
    render();
  }
  open.addEventListener('click', () => toggle(desktop.matches || !body.classList.contains('pv-toc-mobile-open')));
  close.addEventListener('click', () => toggle(false));
  desktop.addEventListener('change', () => { body.classList.remove('pv-toc-mobile-open'); render(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !desktop.matches) toggle(false); });
  const links = [...toc.querySelectorAll('a')];
  links.forEach(a => a.addEventListener('click', () => { if (!desktop.matches) toggle(false); }));
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        links.forEach(a => {
          const active = a.hash.slice(1) === encodeURI(entry.target.id) || decodeURIComponent(a.hash.slice(1)) === entry.target.id;
          a.classList.toggle('active', active);
          if (active) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current');
        });
      });
    }, {rootMargin: '-10% 0px -80% 0px'});
    links.forEach(a => { const target = document.getElementById(decodeURIComponent(a.hash.slice(1))); if (target) io.observe(target); });
  }
  render();
})();
</script>"""


FOLD_SCRIPT = r"""<script>
(() => {
  const key = __FOLD_KEY__;
  const folds = [...document.querySelectorAll('#doc details.pv-fold')];
  if (!folds.length) return;
  let state = {};
  try { state = JSON.parse(localStorage.getItem(key) || '{}'); } catch (_) {}
  const idOf = d => (d.querySelector('summary h1,summary h2,summary h3,summary h4,summary h5,summary h6') || {}).id || '';
  folds.forEach(d => { const id = idOf(d); if (id && state[id]) d.open = true; });
  function save() {
    const next = {};
    folds.forEach(d => { const id = idOf(d); if (id && d.open) next[id] = 1; });
    try { localStorage.setItem(key, JSON.stringify(next)); } catch (_) {}
  }
  folds.forEach(d => d.addEventListener('toggle', save));
  // 收起來的那一行也看得到這段勾完了沒
  function flags() {
    folds.forEach(d => {
      const boxes = [...d.querySelectorAll('input[data-pv-check]')];
      const summary = d.querySelector(':scope > summary');
      if (!summary) return;
      let flag = summary.querySelector('.pv-fold-flag');
      if (!boxes.length) { if (flag) flag.remove(); return; }
      const done = boxes.filter(b => b.checked).length;
      if (!flag) { flag = document.createElement('span'); flag.className = 'pv-fold-flag'; summary.append(flag); }
      flag.textContent = done === boxes.length ? '已勾' : (done ? done + '/' + boxes.length : '待看');
      flag.dataset.done = done === boxes.length ? '1' : '0';
    });
  }
  document.addEventListener('change', e => { if (e.target.matches('input[data-pv-check]')) flags(); });
  flags();
  // 目錄或網址跳到被收起來的段落時，自動把外層打開
  function reveal(hash) {
    if (!hash) return;
    const target = document.getElementById(decodeURIComponent(hash.slice(1)));
    if (!target) return;
    let node = target.closest('details.pv-fold');
    while (node) { node.open = true; node = node.parentElement.closest('details.pv-fold'); }
    save();
    requestAnimationFrame(() => target.scrollIntoView({block: 'start'}));
  }
  addEventListener('hashchange', () => reveal(location.hash));
  reveal(location.hash);
  const bar = document.querySelector('[data-pv-foldall]');
  if (bar) bar.addEventListener('click', () => {
    const open = bar.dataset.state !== 'open';
    folds.forEach(d => { d.open = open; });
    bar.dataset.state = open ? 'open' : 'closed';
    bar.textContent = open ? '全部收合' : '全部展開';
    save();
  });
})();
</script>"""


def make_page(body, title, badges, mode, config, toc_key, fold=False):
    if not re.search(r'<h1\b', body, re.I):
        body = f'<h1>{esc(title)}</h1>\n' + body
    badge_html = '<div class="pv-badges">' + ''.join(f'<span class="pv-badge">{esc(b)}</span>' for b in badges) + '</div>' if badges else ''
    hint = '<p class="pv-hint">框選任何一段文字就能留評論</p>' if mode != 'none' else ''
    if fold:
        hint += ('<div class="pv-foldbar"><button type="button" data-pv-foldall data-state="closed">全部展開</button>'
                 '<span>各段預設收起來，點標題展開</span></div>')
    body = re.sub(r'</h1\s*>', lambda m: m.group(0) + badge_html + hint, body, count=1, flags=re.I)
    body, toc = rebuild_headings(body)
    wide = 'pv-table-wrap--wide' in body or 'pv-vis--wide' in body or any(int(n) >= 3 for n in re.findall(r'--pv-flow-cols:\s*(\d+)', body))
    styles = '\n'.join(path.read_text(encoding='utf-8') for path in (
        _components.parent.parent / 'assets' / 'preview-tokens.css',
        _components / 'components.css', _components / 'visuals.css', _components / 'shell.css'))
    toc_html = '\n'.join(f'<a class="lv{level}" href="#{html.escape(sid, quote=True)}">{esc(label)}</a>' for level, label, sid in toc)
    script = TOC_SCRIPT.replace('__TOC_KEY__', json.dumps('pv_toc_' + toc_key, ensure_ascii=False).replace('<', '\\u003c'))
    fold_script = FOLD_SCRIPT.replace('__FOLD_KEY__', json.dumps('pv_fold_' + toc_key, ensure_ascii=False).replace('<', '\\u003c')) if fold else ''
    page = f'''<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{esc(title)}</title><style>{styles}</style></head>
<body class="{'pv-wide' if wide else ''}">
<button class="pv-toc-open" aria-controls="pv-toc" aria-expanded="false">目錄</button>
<div class="pv-layout"><nav id="pv-toc" class="pv-toc" aria-label="文件目錄">
<button type="button">收合目錄</button>{toc_html}</nav>
<article class="pv-sheet"><main id="doc">{body}</main></article></div>
{HEADING_SCRIPT}
{script}
{fold_script}</body></html>'''
    return injector.inject(page, mode=mode, config=config)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', help='來源 Markdown')
    parser.add_argument('output', help='輸出 HTML')
    for name in ('title', 'key', 'identities', 'badges'):
        parser.add_argument('--' + name)
    parser.add_argument('--no-overlay', action='store_true', help='不注入評論功能（乾淨版）')
    parser.add_argument('--fonts', choices=('copy', 'link', 'none'), default='copy')
    parser.add_argument('--icon', help='分頁小圖示上的字或 emoji（預設取標題第一個字）')
    parser.add_argument('--no-lint', action='store_true', help='不印版面體檢（合約、完稿這類不能改寫的原文用）')
    parser.add_argument('--fold', help='要摺疊的標題層級，逗號分隔（例 "3,4"）；長頁專用，預設不摺')
    args = parser.parse_args(argv)
    src, dst = Path(args.source), Path(args.output)
    fold_levels = {int(x) for x in (args.fold or '').replace('h', '').split(',') if x.strip()}
    try:
        if src.resolve() == dst.resolve() or (dst.exists() and os.path.samefile(src, dst)):
            raise ValueError('輸入與輸出不可使用相同路徑')
        source = src.read_text(encoding='utf-8')
        body, _ = convert(source, fold=fold_levels)
        notes = [] if args.no_lint else visuals.lint(source)
        first = re.search(r'^#\s+(.+)$', source, re.M)
        title = args.title or (plain(inline(first.group(1))) if first else src.stem)
        key = args.key or 'pc_' + dst.stem
        config = dict(title=title, storageKey=key, contentSelector='#doc')
        config['identities'] = ([s.strip() for s in args.identities.split(',') if s.strip()]
                                if args.identities is not None else ['我', '訪客'])
        if not config['identities']:
            raise ValueError('身份清單不可為空')
        mode = 'none' if args.no_overlay else 'local'
        badges = [s.strip() for s in (args.badges or '').split(',') if s.strip()]
        page = make_page(body, title, badges, mode, config, key, fold=bool(fold_levels))
        dst.parent.mkdir(parents=True, exist_ok=True)
        page = injector.ensure_fonts(page, dst, args.fonts)
        page = injector.ensure_favicon(page, title=title, icon=args.icon)
        # 字型區塊放在其他樣式之前，維持資產載入順序。
        font_style = re.search(r'<style\b[^>]*data-pv-fonts[^>]*>.*?</style>', page, re.S | re.I)
        if font_style:
            page = page[:font_style.start()] + page[font_style.end():]
            page = page.replace('<style>', font_style.group(0) + '\n<style>', 1)
        dst.write_text(page, encoding='utf-8')
        print(f'已產出 {dst}｜{len(page):,} 字元')
        if notes:
            print(f'版面體檢：{len(notes)} 項提醒（解說型頁面請改完 md 重跑；原文審稿頁加 --no-lint）')
            for note in notes:
                print('  - ' + note)
        elif not args.no_lint:
            print('版面體檢：通過')
        return 0
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.exit(main())
