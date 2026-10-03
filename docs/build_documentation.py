"""Build a self-contained, printable HTML edition of the project documentation."""
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "DataViz_Pro_Project_Documentation.md"
OUTPUT = ROOT / "DataViz_Pro_Project_Documentation.html"


def inline(value):
    pieces = re.split(r"(`[^`]+`)", value)
    return "".join(
        "<code>" + escape(p[1:-1]) + "</code>" if p.startswith("`")
        else escape(p) for p in pieces
    )


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def render_markdown(source):
    lines = source.splitlines()
    chunks, headings = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            language = line[3:].strip()
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            assert i < len(lines), "Unclosed code fence"
            chunks.append(f'<pre data-language="{escape(language)}"><code>' +
                          escape("\n".join(block)) + "</code></pre>")
            i += 1
            continue
        match = re.match(r"^(#{1,3}) (.+)$", line)
        if match:
            level, text = len(match[1]), match[2]
            anchor = slug(text)
            headings.append((level, text, anchor))
            chunks.append(f'<h{level} id="{anchor}">{inline(text)}</h{level}>')
            i += 1
            continue
        if line.startswith("| "):
            rows = []
            while i < len(lines) and lines[i].startswith("| "):
                values = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in values):
                    rows.append(values)
                i += 1
            assert all(len(r) == len(rows[0]) for r in rows), "Mismatched table columns"
            head = "".join('<th scope="col">' + inline(c) + "</th>" for c in rows[0])
            body = "".join("<tr>" + "".join("<td>" + inline(c) + "</td>" for c in row)
                           + "</tr>" for row in rows[1:])
            chunks.append('<div class="table-scroll"><table><thead><tr>' + head +
                          "</tr></thead><tbody>" + body + "</tbody></table></div>")
            continue
        if re.match(r"^(?:- |\d+\. )", line):
            ordered = bool(re.match(r"^\d+\. ", line))
            pattern = r"^\d+\. (.*)" if ordered else r"^- (.*)"
            items = []
            while i < len(lines) and (item := re.match(pattern, lines[i])):
                text = item[1]
                items.append("<li>" + inline(text) + "</li>")
                i += 1
            tag = "ol" if ordered else "ul"
            chunks.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        paragraph = []
        while i < len(lines) and lines[i].strip():
            if re.match(r"^(?:#{1,3} |```|\| |- |\d+\. )", lines[i]):
                break
            paragraph.append(lines[i])
            i += 1
        chunks.append("<p>" + "<br>".join(inline(p.rstrip()) for p in paragraph) + "</p>")
    return "\n".join(chunks), headings


CSS = """
:root { color-scheme: light; --ink:#17212b; --muted:#566372; --border:#d9d9d9; }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; scroll-padding-top:28px; }
body { margin:0; color:var(--ink); background:#edf0f3; font:16px/1.65 'Segoe UI',Arial,sans-serif; }
.toolbar { padding:13px 28px; background:#172c42; color:white; display:flex; gap:20px; justify-content:space-between; align-items:center; }
.toolbar span { font-size:14px; }
button { cursor:pointer; border:1px solid #bfcbd6; background:white; color:#172c42; padding:9px 16px; border-radius:4px; font:600 14px 'Segoe UI',Arial,sans-serif; }
.layout { display:grid; grid-template-columns:250px minmax(0,930px); gap:36px; max-width:1280px; margin:36px auto; padding:0 26px; }
nav { position:sticky; top:24px; align-self:start; max-height:calc(100vh - 48px); overflow:auto; font-size:13px; }
nav p { margin:0 0 13px; color:#000; font-weight:700; letter-spacing:.06em; font-size:11px; text-transform:uppercase; }
nav a { display:block; color:#435365; text-decoration:none; padding:7px 0; line-height:1.4; }
nav a:hover { color:#000; text-decoration:underline; }
main { background:white; padding:60px 65px; box-shadow:0 3px 20px #172c4210; min-width:0; }
h1,h2,h3 { color:#000; line-height:1.22; break-after:avoid; }
h1 { font-size:38px; font-weight:650; margin:0 0 14px; letter-spacing:-.035em; }
h1 + p { font-size:20px; color:#45586b; margin:0 0 12px; }
h1 + p + p { color:var(--muted); font-size:13px; margin-bottom:40px; }
h2 { margin:42px 0 17px; font-size:25px; font-weight:650; letter-spacing:-.018em; }
h3 { margin:26px 0 10px; font-size:18px; font-weight:650; }
p { margin:0 0 16px; }
li { padding-left:3px; margin:6px 0; }
ul,ol { margin:10px 0 22px; padding-left:25px; }
code { font: .86em/1.5 Consolas,'Courier New',monospace; overflow-wrap:anywhere; }
p code,li code,td code { background:#f3f5f7; padding:1px 3px; }
pre { margin:20px 0 24px; padding:16px 18px; background:#f4f6f8; border:1px solid var(--border); overflow:auto; line-height:1.45; break-inside:avoid; }
pre code { font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; }
.table-scroll { overflow-x:auto; margin:18px 0 25px; }
table { width:100%; border-collapse:collapse; table-layout:auto; font-size:13px; line-height:1.5; }
th,td { border:1px solid var(--border); padding:11px 12px; vertical-align:middle; overflow-wrap:anywhere; text-align:left; }
th { background:#223c55; color:#fff; font-weight:600; }
tr:nth-child(even) td { background:#f2f5f8; }
tr { break-inside:avoid; }
thead { display:table-header-group; }
td:first-child { min-width:76px; }
footer { font-size:12px; color:#65717b; margin:44px 0 0; }
@media(max-width:950px) { .layout { display:block; padding:0 16px; margin:20px auto; } nav { display:none; } main { padding:32px 26px; } h1 {font-size:32px;} }
@media print {
  @page { size:Letter; margin:.7in .7in .75in; }
  body { font:11pt/1.45 Arial,sans-serif; background:white; color:#111; }
  .toolbar,nav { display:none; }
  .layout { display:block; max-width:none; padding:0; margin:0; }
  main { padding:0; box-shadow:none; }
  h1 { font-size:29pt; margin-top:18pt; }
  h2 { font-size:18pt; margin-top:24pt; }
  h3 { font-size:13pt; margin-top:16pt; }
  p { orphans:3; widows:3; margin-bottom:10pt; }
  table { font-size:9pt; }
  th,td { padding:7pt 8pt; }
  th { background:#e9eef3 !important; color:#000 !important; }
  .table-scroll { overflow:visible; }
  pre { padding:10pt; background:#f8f8f8; }
  pre code { font-size:9pt; }
  a { color:inherit; text-decoration:none; }
  #contents + ol { columns:2; column-gap:25pt; font-size:10pt; }
  #abstract { margin-top:25pt; }
}
"""


class Checker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links = [], []
        self.tables = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if attrs.get("href", "").startswith("#"):
            self.links.append(attrs["href"][1:])
        if tag == "table":
            self.tables += 1


def main():
    source = SOURCE.read_text(encoding="utf-8")
    body, headings = render_markdown(source)
    chapters = [(text, anchor) for level, text, anchor in headings
                if level == 2 and re.match(r"\d+ ", text)]
    assert len(chapters) == 15
    toc = '<ol>' + ''.join(f'<li><a href="#{anchor}">{escape(re.sub(r"^\d+ ", "", title))}</a></li>'
                         for title, anchor in chapters) + '</ol>'
    body = re.sub(r'(<h2 id="contents">Contents</h2>\s*)<ol>.*?</ol>',
                  lambda m: m[1] + toc, body, count=1, flags=re.S)
    nav = ''.join(f'<a href="#{anchor}">{escape(title)}</a>' for title, anchor in chapters)
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="DataViz Pro technical documentation and final year project report">
<title>DataViz Pro Project Documentation</title><style>{CSS}</style></head>
<body><div class="toolbar"><span>DataViz Pro · Project documentation · 19 September 2026</span>
<button type="button" onclick="window.print()">Print or save as PDF</button></div>
<div class="layout"><nav aria-label="Document contents"><p>On this page</p>{nav}</nav>
<main>{body}<footer>DataViz Pro · Version 2.0.0 · Project documentation</footer></main></div></body></html>'''
    check = Checker()
    check.feed(page)
    assert len(check.ids) == len(set(check.ids)), 'Duplicate heading IDs'
    assert all(link in check.ids for link in check.links), 'Broken document links'
    assert check.tables == sum(line.startswith('| ---') for line in source.splitlines()), 'Table conversion mismatch'
    OUTPUT.write_text(page, encoding="utf-8")
    print(f'Created {OUTPUT.name}: {len(chapters)} chapters, {len(headings)} headings, {check.tables} tables, {len(source.split())} words')


if __name__ == '__main__':
    main()
