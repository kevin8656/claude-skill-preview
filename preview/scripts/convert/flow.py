"""保守辨識流程圖；無法完整理解時交回原始區塊。"""
from __future__ import annotations  # 讓 Python 3.9（macOS 內建）也能跑
import html
import re
from html.parser import HTMLParser


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _plain(value):
    parser = _Text()
    parser.feed(value)
    return ''.join(parser.parts)


def _preserved(source, output):
    # 忽略排版標記，但逐段核對中日韓文字及英數詞。
    words = re.findall(r'[一-鿿぀-ヿ가-힣]+|[A-Za-z0-9]+', source)
    text = _plain(output)
    return all(word in text for word in words)


def _row(labels, inline, single=False):
    items = []
    for label in labels:
        match = re.match(r'^([A-Z]{1,3}\d{1,2})\b\s*(.*)$', label)
        badge = ''
        if match:
            badge = '<span class="pv-flow-code">' + inline(match[1]) + '</span>'
            label = match[2]
        items.append('<li class="pv-flow-step">' + badge +
                     '<span class="pv-flow-label">' + inline(label) + '</span></li>')
    extra = ' pv-flow-row--single' if single else ''
    return '<ol class="pv-flow-row' + extra + '">' + ''.join(items) + '</ol>'


def _ascii(lines, inline):
    source = '\n'.join(lines)
    arrow = r'→|↓|-->|->|=>'
    if not re.search(r'[─-╿]|' + arrow, source):
        return None
    if sum(bool(re.search(r'[一-鿿぀-ヿ가-힣]|' + arrow, line)) for line in lines) * 2 < len(lines):
        return None
    if re.search(r'[{}]|;\s*$|(?<![=<>!])=(?!=|>)|^\s*\$ |\b(?:def\s|function\b|SELECT\b|import\s)', source, re.M | re.I):
        return None
    if re.search(r'^\s*(?:[A-Za-z_][\w.]*\s*\(|(?:echo|printf|cd|npm|npx|node|python3?|bash|sh|curl|wget|export|return|const|let|var)\s)', source, re.M):
        return None
    trees = [line for line in lines if re.match(r'^\s*[│ ]*[├└]──\s*\S', line) and not re.search(r'[┘┤]\s*$', line)]
    if len(trees) >= 2:
        return None
    result, pending = [], []

    def flush():
        if pending:
            result.append(_row(pending, inline, len(pending) == 1))
            pending.clear()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if re.fullmatch(r'[│↓|→\s]+', line):
            continue
        if '┌' in line and ('┬' in line or '┐' in line):
            flush()
            if re.sub(r'[─┌┬┐\s]', '', line):
                return None
            columns = []
            closed = False
            while i < len(lines):
                branch = lines[i].strip()
                i += 1
                if '└' in branch or '┘' in branch:
                    note = re.sub(r'[─└┘┴]', '', branch).strip()
                    closed = True
                    break
                if re.fullmatch(r'[│↓|\s]+', branch):
                    continue
                cells = re.split(r'\s{2,}', branch)
                if not columns:
                    if len(cells) < 2:
                        return None
                    columns = [[cell] for cell in cells]
                elif len(cells) != len(columns):
                    return None
                else:
                    for column, cell in zip(columns, cells):
                        column.append(cell)
            if not closed or not columns:
                return None
            result.append('<div class="pv-flow-branches" style="--pv-flow-cols:' + str(len(columns)) + '">')
            for column in columns:
                result.append('<div class="pv-flow-branch"><div class="pv-flow-cond">' + inline(column[0]) + '</div>' +
                              ''.join('<div class="pv-flow-desc">' + inline(cell) + '</div>' for cell in column[1:]) + '</div>')
            result.append('</div>')
            if note:
                result.append('<p class="pv-flow-note">' + inline(note) + '</p>')
            continue
        nodes = [part.strip() for part in re.split(r'─{2,}|-->|->|=>|→', line)]
        if len(nodes) > 1:
            if not all(nodes) or any(re.search(r'[─-╿]', node) for node in nodes):
                return None
            flush()
            result.append(_row(nodes, inline))
        else:
            label = line.strip('│| ').strip()
            if not label or re.search(r'[─-╿→↓]', label) or re.search(r'\s{2,}', label):
                return None
            pending.append(label)
    flush()
    return ''.join(result) if result else None


def _mermaid(source, inline):
    header = re.match(r'^\s*(?:graph|flowchart)\s+(?:TD|TB|LR)\b\s*(?:;|\n|$)', source)
    if not header:
        return None
    nodes, edges, indegree = {}, {}, {}
    payload = []
    node_re = re.compile(r'\s*([A-Za-z][A-Za-z0-9_]*)(?:\[([^\[\]\n]+)\]|\(([^()\n]+)\)|\{([^{}\n]+)\})?')

    def node(text, pos):
        match = node_re.match(text, pos)
        if not match:
            raise ValueError()
        key = match[1]
        if key in ('subgraph', 'end', 'style', 'class', 'classDef', 'linkStyle', 'click', 'direction'):
            raise ValueError()
        label = next((item for item in match.groups()[1:] if item is not None), None)
        if label is not None:
            if key in nodes and nodes[key] not in (None, label):
                raise ValueError()
            nodes[key] = label
        else:
            nodes.setdefault(key, None)
        edges.setdefault(key, [])
        indegree.setdefault(key, 0)
        return key, match.end()

    try:
        for statement in re.split(r'[;\n]', source[header.end():]):
            if not statement.strip():
                continue
            start, pos = node(statement, 0)
            while statement[pos:].strip():
                edge = re.match(r'\s*(-->|---)\s*(?:\|([^|\n]+)\|\s*)?', statement[pos:])
                if not edge:
                    return None
                end, pos = node(statement, pos + edge.end())
                edges[start].append((end, edge[2]))
                indegree[end] += 1
                start = end
        roots = [key for key in nodes if indegree[key] == 0]
        if len(roots) != 1 or any(value > 1 for value in indegree.values()):
            return None
        visited = set()

        def render(key):
            chain, output = [], []
            while True:
                if key in visited:
                    raise ValueError()
                visited.add(key)
                label = nodes[key] if nodes[key] is not None else key
                payload.append(label)
                chain.append(label)
                children = edges[key]
                if len(children) != 1 or children[0][1]:
                    break
                key = children[0][0]
            output.append(_row(chain, inline))
            if children:
                output.append('<div class="pv-flow-branches" style="--pv-flow-cols:' + str(len(children)) + '">')
                for child, condition in children:
                    output.append('<div class="pv-flow-branch">')
                    if condition:
                        payload.append(condition)
                        output.append('<div class="pv-flow-cond">' + inline(condition) + '</div>')
                    output.append(render(child))
                    output.append('</div>')
                output.append('</div>')
            return ''.join(output)

        output = render(roots[0])
        if len(visited) != len(nodes) or not _preserved(' '.join(payload), output):
            return None
        return output
    except (ValueError, RecursionError):
        return None


def convert_block(lang: str, lines: list[str], inline=None) -> str | None:
    """回傳可保全資訊的流程卡片；不支援的區塊回傳 None。"""
    inline = inline or html.escape
    lines = [line for line in lines if line.strip()]
    if not lines:
        return None
    source = '\n'.join(lines)
    if lang == 'mermaid':
        output = _mermaid(source, inline)
    elif lang in ('', 'text', 'txt', 'flow'):
        output = _ascii(lines, inline)
        if output and not _preserved(source, output):
            return None
    else:
        return None
    return '<figure class="pv-flow">' + output + '</figure>' if output else None
