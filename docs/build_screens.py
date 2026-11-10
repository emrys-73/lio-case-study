import re
from pathlib import Path

DOCS = Path(__file__).parent
PARTS = DOCS / "screens-parts"
PROBLEMS = [
    ("p1", "1", "PDF Extraction"),
    ("p2", "2", "Negotiated Prices"),
    ("p3", "3", "Commodity Groups"),
    ("p4", "4", "Approval Limit"),
]
STEP = re.compile(r'<h2 id="([^"]+)"([^>]*)><span class="badge[^"]*">([^<]+)</span>([^<]+)</h2>')


def flow(part):
    pills = "".join(
        f'<a href="#{i}"{' class="is-later"' if "data-later" in a else ""}><span class="badge">{b}</span>{t}</a>' for i, a, b, t in STEP.findall(part)
    )
    return f'\n  <div class="flow">{pills}</div>\n'


def main():
    head = (PARTS / "head.html").read_text()
    logo = (PARTS / "logo.html").read_text().strip()
    sections, nav = [], []
    for key, num, title in PROBLEMS:
        f = PARTS / f"{key}.html"
        if not f.exists():
            continue
        part = f.read_text()
        steps = flow(part)
        part = re.sub(r'(<div class="prob-head">.*?</p></div>)', lambda m: m.group(1) + steps, part, count=1, flags=re.S)
        sections.append(part)
        nav.append(f'<a href="#{key}"><b>{num}</b>{title}</a>')
    top = f'''<main class="wrap">

  <div class="top">
    {logo}
    <span class="kicker">SCREENS</span>
  </div>

  <h1>Lio Screens</h1>
  <p class="sub">Every UI change for problems 1 to 4, pick one per step</p>
  <div class="nav"><a href="https://claude.ai/artifact/2WE1vvNYGuj9t99Z37f6w5">Playbook ↗</a><a href="https://claude.ai/artifact/2wyQCsPwmHWkDDEDTkAdz4">App Map ↗</a><a href="https://claude.ai/artifact/1kRAbazDyn3sEAkcK2ckP5">Case Study ↗</a><span class="here">Screens</span></div>
  <div class="pnav">{"".join(nav)}</div>
'''
    foot = '''
  <footer><span>Lio screens. Three options per step, one pick. Frontend built against each contract, backend apart.</span><span>Lio FDE case study</span></footer>
</main>
'''
    out = head + top + "\n".join(sections) + foot
    (DOCS / "problem-2-screens.html").write_text(out)
    print("wrote problem-2-screens.html", len(out), "sections", len(sections))


if __name__ == "__main__":
    main()
