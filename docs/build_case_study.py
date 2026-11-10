import pathlib
import re
import sys

DOCS = pathlib.Path(__file__).parent
ALL = "https://claude.ai/artifact/1kRAbazDyn3sEAkcK2ckP5"

PAGES = [
    ("problem-1", "1", "PDF Extraction", "Quotes come out wrong, empty, or crash", "problem-1-extraction.html", "https://claude.ai/artifact/UtevwtC6sm7Xkag6ZXdJ2x", ""),
    ("problem-2", "2", "Negotiated Prices", "Suggest Acme's catalogue articles on a request", "problem-2-prices.html", "https://claude.ai/artifact/Md6pmuSKugrVPTqJ8VfJxC", ""),
    ("problem-3", "3", "Commodity Groups", "Acme's categories don't match its books", "problem-3-categories.html", "https://claude.ai/artifact/GREGtJRcVsswTD8zhvEWgK", ""),
    ("problem-4", "★", "Approval Limit", "No buyer sign-off under €2,000", "problem-4-approval.html", "https://claude.ai/artifact/JuwhuY7yNAAWq8Bw7jP6kq", " bonus"),
]


def body_of(text):
    start = re.search(r'<div class="nav">.*?</div>\n', text, re.S).end()
    end = text.index("<footer")
    return text[start:end].rstrip()


def localise(html):
    for anchor, _, _, _, _, url, _ in PAGES:
        html = html.replace(f'href="{url}"', f'href="#{anchor}"')
    html = re.sub(r'href="' + re.escape(ALL) + r'#', 'href="#', html)
    html = re.sub(r'(<a href="#[^"]*">[^<]*?) ↗</a>', r"\1</a>", html)
    html = html.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")
    return html


def main():
    src = (DOCS / "case-study.src.html").read_text()
    css = re.search(r"<style>\n(.*?)</style>", (DOCS / "problem-3-categories.html").read_text(), re.S).group(1)
    sections = []
    for anchor, badge, title, what, filename, url, extra in PAGES:
        inner = localise(body_of((DOCS / filename).read_text()))
        sections.append(
            f'  <details class="prob{extra}" id="{anchor}">\n'
            f'    <summary><span class="badge">{badge}</span><h3>{title}</h3>'
            f'<span class="what">{what}</span><span class="toggle"></span></summary>\n'
            f'    <div class="in">\n{inner}\n'
            f'    <p class="pagelink"><a href="{url}">This problem on its own page ↗</a></p>\n'
            f"    </div>\n  </details>"
        )
    out = src.replace("/*STYLE*/\n", css).replace("<!--PROBLEMS-->", "\n".join(sections))
    if ALL in out:
        sys.exit("link to this page left in output")
    (DOCS / "case-study.html").write_text(out)
    print("wrote case-study.html", len(out))


main()
