#!/usr/bin/env python3
"""把框選評論介面與字型注入一份已經排好版的 HTML（例如自己做好的提案頁、銷售頁）。只用標準函式庫。"""
from __future__ import annotations  # 讓 Python 3.9（macOS 內建）也能跑
import html as _html  # 檔內函式參數多半叫 html，用別名避免撞名
import argparse
import json
import os
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

# 技能資料夾裡的 assets/（本檔在 scripts/convert/ 底下）
ASSETS = Path(__file__).resolve().parents[2] / 'assets'


class _Spans(HTMLParser):
    """保留原始位移，避免重新序列化宿主頁面。"""
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0]
        self.lines.extend(m.end() for m in re.finditer('\n', source))
        self.stack = []
        self.nodes = []
        self.feed(source)

    def pos(self):
        row, col = self.getpos()
        return self.lines[row - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'div'):
            self.stack.append((tag, self.pos(), dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                _, start, attrs = self.stack.pop(i)
                end = self.source.find('>', self.pos()) + 1
                self.nodes.append((start, end, tag, attrs))
                break

    def handle_comment(self, data):
        self.nodes.append((self.pos(), self.pos() + len(data) + 7, 'comment', {}))


def strip_overlay(html: str) -> str:
    """只移除介面本體及緊鄰的樣式、程式與檔頭，設定保留。"""
    nodes = _Spans(html).nodes
    spans = []
    for start, end, tag, attrs in nodes:
        if tag != 'div' or not {'pc-overlay-root', 'pco-root'}.intersection(attrs.get('class', '').split()):
            continue
        left, right = start, end
        before = sorted((n for n in nodes if n[1] <= start), key=lambda n: n[1], reverse=True)
        for a, b, kind, _ in before:
            if html[b:left].strip():
                break
            text = html[a:b]
            if kind == 'style' and re.search(r'\.(?:pc-overlay-root|pco-root)\b', text):
                left = a
            elif kind == 'comment' and ('overlay' in text or not text.strip('<!-> \n')):
                left = a
            else:
                break
        after = sorted((n for n in nodes if n[0] >= end), key=lambda n: n[0])
        for a, b, kind, _ in after:
            if html[right:a].strip():
                break
            text = html[a:b]
            if kind == 'script' and re.search(r'PreviewComments\s*=', text):
                right = b
                break
            if kind == 'comment' and 'overlay' in text:
                right = b
            else:
                break
        spans.append((left, right))
    for start, end in sorted(spans, reverse=True):
        html = html[:start] + html[end:]
    return html


class _Literal:
    """只讀資料字面值，不執行頁面中的 JavaScript。"""
    def __init__(self, source):
        self.source, self.i = source, 0

    def skip(self):
        match = re.match(r'(?:\s+|//[^\n]*(?:\n|$)|/\*[\s\S]*?\*/)*', self.source[self.i:])
        self.i += match.end()

    def read(self):
        self.skip()
        char = self.source[self.i:self.i + 1]
        if char in ('"', "'"):
            value, self.i = _js_string(self.source, self.i)
            return value
        if char in ('{', '['):
            closing = '}' if char == '{' else ']'
            result = {} if char == '{' else []
            self.i += 1
            self.skip()
            while self.source[self.i:self.i + 1] != closing:
                if char == '{':
                    self.skip()
                    if self.source[self.i:self.i + 1] in ('"', "'"):
                        key = self.read()
                    else:
                        match = re.match(r'[A-Za-z_$][\w$]*', self.source[self.i:])
                        if not match:
                            raise ValueError('無法讀取設定欄位')
                        key = match[0]
                        self.i += match.end()
                    self.skip()
                    if self.source[self.i:self.i + 1] != ':':
                        raise ValueError('設定欄位缺少冒號')
                    self.i += 1
                    result[key] = self.read()
                else:
                    result.append(self.read())
                self.skip()
                if self.source[self.i:self.i + 1] == ',':
                    self.i += 1
                    self.skip()
                elif self.source[self.i:self.i + 1] != closing:
                    raise ValueError('設定欄位缺少逗號')
            self.i += 1
            return result
        match = re.match(r'true\b|false\b|null\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', self.source[self.i:])
        if not match:
            raise ValueError('設定含不支援的運算式，請改用資料字面值')
        self.i += match.end()
        return json.loads(match[0])


def _js_string(source, start):
    """依 JavaScript 規則解碼引號字串，不借用其他語言的跳脫語意。"""
    quote_char, i, chars = source[start], start + 1, []
    escapes = {'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t', 'v': '\v'}
    while i < len(source):
        char = source[i]
        i += 1
        if char == quote_char:
            value = ''.join(chars)
            # JavaScript 的兩個 UTF-16 代理碼須還原為同一個 Unicode 字元。
            return value.encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'surrogatepass'), i
        if char in '\r\n':
            raise ValueError('設定字串含未跳脫的換行')
        if char != '\\':
            chars.append(char)
            continue
        if i >= len(source):
            break
        char = source[i]
        i += 1
        if char in '\r\n':
            if char == '\r' and source[i:i + 1] == '\n':
                i += 1
            continue
        if char in ('\u2028', '\u2029'):
            continue
        if char in escapes:
            chars.append(escapes[char])
        elif char in ('x', 'u'):
            if char == 'u' and source[i:i + 1] == '{':
                end = source.find('}', i + 1)
                digits = source[i + 1:end] if end >= 0 else ''
                i = end + 1
            else:
                count = 2 if char == 'x' else 4
                digits, i = source[i:i + count], i + count
                if len(digits) != count:
                    raise ValueError('設定字串的字元碼長度不正確')
            if not re.fullmatch(r'[0-9a-fA-F]+', digits) or int(digits, 16) > 0x10ffff:
                raise ValueError('設定字串的字元碼無效')
            chars.append(chr(int(digits, 16)))
        elif char in '01234567':
            # 非嚴格模式既有頁面可能使用八進位跳脫。
            limit = 3 if char in '0123' else 2
            digits = char
            while len(digits) < limit and source[i:i + 1] and source[i] in '01234567':
                digits += source[i]
                i += 1
            chars.append(chr(int(digits, 8)))
        else:
            chars.append(char)
    raise ValueError('設定字串未結束')


def _assignments(script, name):
    """略過註解與字串，只在程式區域找設定賦值。"""
    pattern = re.compile(r'(?:window\s*\.\s*)?' + re.escape(name) + r'\s*=\s*(?=\{)')
    i = 0
    while i < len(script):
        if script.startswith('//', i):
            end = script.find('\n', i + 2)
            i = end + 1 if end >= 0 else len(script)
        elif script.startswith('/*', i):
            end = script.find('*/', i + 2)
            i = end + 2 if end >= 0 else len(script)
        elif script[i] in ('"', "'"):
            _, i = _js_string(script, i)
        elif script[i] == '`':
            # 樣板字串視為資料，避免範例設定被誤認為有效設定。
            i += 1
            while i < len(script):
                if script[i] == '\\':
                    i += 2
                elif script[i] == '`':
                    i += 1
                    break
                else:
                    i += 1
        else:
            match = pattern.match(script, i) if i == 0 or not re.match(r'[\w$.]', script[i - 1]) else None
            if match:
                literal = _Literal(script[match.end():])
                value = literal.read()
                yield value
                i = match.end() + literal.i
            else:
                i += 1


def read_config(html: str, name: str) -> dict:
    result = {}
    for start, end, tag, _ in sorted(_Spans(html).nodes):
        if tag != 'script':
            continue
        script = html[start:end]
        script = script[script.find('>') + 1:script.rfind('</')]
        for value in _assignments(script, name):
            if isinstance(value, dict):
                result.update(value)
    return result


_CONFIG_ONLY = re.compile(r'^<script\b[^>]*>\s*window\.PREVIEW_CONFIG\s*=\s*\{[\s\S]*\}\s*;?\s*</script\s*>$', re.I)


def strip_config(html: str) -> str:
    """移除「整段只有設定賦值」的 script（例如舊頁的設定、或手動先放的設定）。
    注入時會用讀出來的設定重寫一份，不先移除的話頁面會疊兩份設定。
    設定 script 裡混了其他程式（例如另外掛 onBeforeScroll 函式）就不動，避免把手寫邏輯刪掉。"""
    spans = [(a, b) for a, b, kind, _ in _Spans(html).nodes if kind == 'script' and _CONFIG_ONLY.match(html[a:b])]
    for a, b in sorted(spans, reverse=True):
        end = b + 1 if html[b:b + 1] == '\n' else b
        html = html[:a] + html[end:]
    return html


def inject(html: str, *, mode: str, config: dict, overlay_path=None) -> str:
    if mode == 'none':
        return html
    if mode != 'local':
        raise ValueError('模式必須是 local 或 none')
    # 頁面沒有 #doc 時，評論介面會自動退回整頁。
    config = dict({'contentSelector': '#doc'}, **config)
    name = 'PREVIEW_CONFIG'
    path = Path(overlay_path) if overlay_path else ASSETS / 'preview-comment-overlay.html'
    payload = json.dumps(config, ensure_ascii=False).replace('<', '\\u003c')
    insertion = f'<script>window.{name} = {payload};</script>\n' + path.read_text(encoding='utf-8') + '\n'
    match = find_tag(html, r'</body\s*>')
    if not match:
        # 沒有 </body> 的頁面：瀏覽器本來就容許缺結尾標籤，接在檔尾即可
        return html.rstrip('\n') + '\n' + insertion
    return html[:match.start()] + insertion + html[match.start():]


_RAW_BLOCK = re.compile(r'<!--[\s\S]*?-->|<style\b[^>]*>[\s\S]*?</style\s*>|<script\b[^>]*>[\s\S]*?</script\s*>', re.I)


def find_tag(html: str, pattern: str):
    """找真正的結尾標籤（例如 </head>、</body>），跳過註解、<style>、<script> 裡面的同名字樣。
    例如頁面 CSS 註解裡寫了「</head> 之前」，直接找第一個會把字型樣式插進頁面自己的 <style> 中間、弄壞版面。"""
    blocked = [(m.start(), m.end()) for m in _RAW_BLOCK.finditer(html)]
    for m in re.finditer(pattern, html, re.I):
        if not any(a < m.start() < b for a, b in blocked):
            return m
    return None


_ICON_SKIP = re.compile(r'[\s\d\W_]', re.U)


def favicon_link(title: str = '', icon: str = None) -> str:
    """分頁小圖示：深墨藍圓角方塊中間放一個字（預設取標題第一個字），SVG 內嵌成 data URI，不需要另外的檔案。
    預覽頁分頁一多時，才分得出哪個分頁是哪一頁。"""
    glyph = (icon or '').strip()
    if not glyph:
        glyph = next((ch for ch in (title or '') if not _ICON_SKIP.match(ch)), '評')
    glyph = glyph[:2]
    size = 36 if len(glyph) == 1 else 26
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<rect width="64" height="64" rx="14" fill="#1F3A5F"/>'
           f'<text x="32" y="33" font-size="{size}" font-weight="700" fill="#fff" text-anchor="middle" dominant-baseline="central" '
           'font-family="PingFang TC,Noto Sans TC,Microsoft JhengHei,sans-serif">' + _html.escape(glyph) + '</text></svg>')
    from urllib.parse import quote
    return f'<link rel="icon" href="data:image/svg+xml,{quote(svg)}" data-pv-icon>'


def ensure_favicon(page: str, title: str = None, icon: str = None) -> str:
    """頁面已經有 favicon（例如銷售頁自己的品牌圖示）就不動；沒有才補預設小圖示。"""
    if re.search(r'<link\b[^>]*\brel=["\x27]?(?:shortcut\s+)?icon', page, re.I):
        return page
    if title is None:
        m = re.search(r'<title\b[^>]*>(.*?)</title>', page, re.S | re.I)
        title = _html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip() if m else ''
    link = favicon_link(title, icon)
    m = find_tag(page, r'</head\s*>')
    return page[:m.start()] + link + '\n' + page[m.start():] if m else link + page


SCOPED_FAMILIES = {"'Noto Sans TC'": "'PV Noto Sans TC'", "'Geist Mono'": "'PV Geist Mono'", "'Geist'": "'PV Geist'"}
SCOPED_OVERRIDE = ("\n/* 注入既有頁面專用：評論工具的字型改用專屬名稱，不跟頁面自己的同名字型（例如 Google Fonts 的 Noto Sans TC）搶名字。\n"
                   "   同名時頁面正文的英數會被這裡的子集接管。選擇器權重要高過評論工具自己的 token 區塊。 */\n"
                   "html body .pco-root, html body .pc-overlay-root {"
                   " --pv-font-sans: 'PV Noto Sans TC', 'PV Geist', system-ui, sans-serif;"
                   " --pv-font-mono: 'PV Geist Mono', 'PV Noto Sans TC', ui-monospace, monospace; }\n")


def ensure_fonts(html: str, out_path, fonts_mode: str, url_prefix: str = None, scoped: bool = False) -> str:
    """url 模式：不複製，字型網址用 url_prefix（例如網站根目錄共用一份，頁面寫 ../preview-fonts/）。
    scoped=True：注入到不是產生器產的頁時用，字型名稱加 PV 前綴、只給評論工具用，頁面本身的字一個都不受影響。"""
    if fonts_mode not in ('copy', 'link', 'none', 'url'):
        raise ValueError('字型模式必須是 copy、link、url 或 none')
    if fonts_mode == 'url' and not url_prefix:
        raise ValueError('字型 url 模式要給 --fonts-url')
    if fonts_mode == 'none':
        return re.sub(r'<style\b[^>]*\bdata-pv-fonts\b[^>]*>[\s\S]*?</style\s*>', '', html, flags=re.I)
    fonts = ASSETS / 'fonts'
    out_dir = Path(out_path).resolve().parent
    if fonts_mode == 'copy':
        target = out_dir / 'preview-fonts'
        target.mkdir(parents=True, exist_ok=True)
        for source in fonts.glob('*.woff2'):
            dest = target / source.name
            if not dest.exists() or dest.stat().st_size != source.stat().st_size:
                shutil.copyfile(source, dest)
        prefix = 'preview-fonts/'
    elif fonts_mode == 'url':
        prefix = url_prefix if url_prefix.endswith('/') else url_prefix + '/'
    else:
        prefix = quote(os.path.relpath(fonts, out_dir).replace(os.sep, '/'), safe='/') + '/'
    css = (fonts / 'preview-fonts.css').read_text(encoding='utf-8').replace('preview-fonts/', prefix)
    if scoped:
        for a, b in SCOPED_FAMILIES.items():
            css = css.replace(f'font-family:{a}', f'font-family:{b}').replace(f'font-family: {a}', f'font-family: {b}')
        css += SCOPED_OVERRIDE
    style = '<style data-pv-fonts>\n' + css + '\n</style>\n'
    pattern = r'<style\b[^>]*\bdata-pv-fonts\b[^>]*>[\s\S]*?</style\s*>'
    if re.search(pattern, html, re.I):
        return re.sub(pattern, lambda _: style, html, count=1, flags=re.I)
    match = find_tag(html, r'</head\s*>')
    if not match:
        # 有些舊頁整份沒有 <html><head><body>（瀏覽器會自動補），就接在 </title> 後面，再不行放檔頭
        title = re.search(r'</title\s*>\n?', html, re.I)
        at = title.end() if title else 0
        return html[:at] + style + html[at:]
    return html[:match.start()] + style + html[match.start():]


def main(argv=None):
    parser = argparse.ArgumentParser(description='把框選評論介面注入一份新的 HTML（不覆蓋來源）')
    parser.add_argument('source', help='來源 HTML')
    parser.add_argument('-o', required=True, help='新的輸出 HTML')
    parser.add_argument('--local', action='store_true', help='單機評論（預設就是，保留這個參數相容舊指令）')
    parser.add_argument('--replace', action='store_true', help='替換頁面上既有的評論介面')
    parser.add_argument('--fonts', choices=['copy', 'link', 'url', 'none'], default='copy', help='字型處理方式')
    parser.add_argument('--fonts-url', help='--fonts url 時的字型網址前綴，例如 ../preview-fonts/')
    parser.add_argument('--no-icon', action='store_true', help='不補分頁小圖示')
    parser.add_argument('--identities', help='身份清單，逗號分隔，第一個是預設身份')
    parser.add_argument('--title', help='匯出彙整用的文件標題')
    parser.add_argument('--key', help='localStorage 鍵，每頁唯一')
    parser.add_argument('--icon', help='分頁小圖示上的字或 emoji（預設取頁面標題第一個字；頁面已有 favicon 就不動）')
    args = parser.parse_args(argv)
    source, output = Path(args.source), Path(args.o)
    if source.resolve() == output.resolve() or (output.exists() and os.path.samefile(source, output)):
        parser.error('輸入與輸出必須是不同檔案，禁止覆蓋來源')
    try:
        html = source.read_text(encoding='utf-8')
        config = read_config(html, 'PREVIEW_CONFIG')
        if args.identities is not None:
            config['identities'] = [x.strip() for x in args.identities.split(',') if x.strip()]
            if not config['identities']:
                raise ValueError('身份清單不可為空')
        if args.title is not None:
            config['title'] = args.title
        if args.key is not None:
            config['storageKey'] = args.key
        config.setdefault('storageKey', 'pc_' + output.stem)
        config.setdefault('identities', ['我', '訪客'])
        if args.replace:
            html = strip_overlay(html)
        elif any(n[2] == 'div' and {'pc-overlay-root', 'pco-root'}.intersection(n[3].get('class', '').split()) for n in _Spans(html).nodes):
            raise ValueError('頁面已有評論介面，請加 --replace')
        html = strip_config(html)
        html = inject(html, mode='local', config=config)
        # 注入的都是「不是產生器產的頁」，字型一律用專屬名稱，避免改到頁面本身的字
        html = ensure_fonts(html, output, args.fonts, args.fonts_url, scoped=True)
        if not args.no_icon:
            html = ensure_favicon(html, icon=args.icon)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(html, encoding='utf-8')
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f'已產生：{output}')


if __name__ == '__main__':
    main()
