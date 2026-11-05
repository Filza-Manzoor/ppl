"""Bayan look and feel: styles, logo and the result card.

Everything that reaches the HTML from a photo, a database or a model goes
through esc(), because the result card is rendered as raw HTML.
"""
from __future__ import annotations

import html

from . import rules

NAME = "Ppl"
TAGLINE = "Good food travels between friends."

VERDICT_WORD = {
    rules.NOT_HALAL: "Not halal",
    rules.DOUBTFUL: "Doubtful",
    rules.LOOKS_HALAL: "Looks halal",
    rules.UNKNOWN: "Can't tell yet",
}
VERDICT_CLASS = {
    rules.NOT_HALAL: "v-no",
    rules.DOUBTFUL: "v-doubt",
    rules.LOOKS_HALAL: "v-ok",
    rules.UNKNOWN: "v-unk",
}
CHIP = {
    "prohibited": ("Avoid", "c-no"),
    "doubtful": ("Doubtful", "c-doubt"),
    "check": ("Check", "c-check"),
}


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


LOGO_SVG = (
    '<svg role="img" aria-label="Ppl logo" width="38" height="38" viewBox="0 0 38 38" xmlns="http://www.w3.org/2000/svg"><rect width="38" height="38" rx="10.5" fill="#fff"/><path d="M13 32 V14" stroke="#111" stroke-width="4" stroke-linecap="round"/><circle cx="21.5" cy="15" r="7.6" fill="none" stroke="#111" stroke-width="4"/><path d="M21.5 18 C18.4 17.4 18.4 12.6 22.4 11.8 C23.6 14 23.4 16.6 21.5 18z" fill="#2FA84F"/><circle cx="24" cy="16.4" r="1.7" fill="#C8102E"/></svg>'
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=DM+Sans:wght@400;500;600;700&display=swap');
:root{--ink:#101828;--cobalt:#2747D8;--mist:#F5F6FA;--line:#E3E6EF;--muted:#5B6585}
header[data-testid="stHeader"],footer,#MainMenu,[data-testid="stToolbar"],[data-testid="stDecoration"]{display:none!important}
.stApp{background:var(--mist);color:var(--ink)}
.block-container{max-width:520px;padding:1.1rem 1rem 3rem}
.stApp p,.stApp li,.stApp label,.stApp input,.stApp textarea,.stApp button,.stApp [data-baseweb="select"] div{font-family:'DM Sans',system-ui,-apple-system,'Segoe UI',sans-serif}

.brand{display:flex;align-items:center;gap:.6rem;margin:.1rem 0 1rem}
.brand .name{font-family:'Bricolage Grotesque','DM Sans',system-ui,sans-serif;font-weight:800;font-size:1.65rem;letter-spacing:-.02em;color:var(--ink)}
.hero{font-family:'Bricolage Grotesque','DM Sans',system-ui,sans-serif;font-weight:800;font-size:2rem;line-height:1.08;letter-spacing:-.025em;margin:0 0 .4rem;color:var(--ink)}
.sub{color:var(--muted);font-size:1rem;line-height:1.45;margin:0 0 1.1rem}

div[data-baseweb="tab-list"],[role="tablist"]{gap:.3rem!important;background:#E8EBF4!important;padding:.25rem!important;border-radius:14px!important;border:0!important;box-shadow:none!important}
button[data-baseweb="tab"],[role="tab"]{flex:1;justify-content:center;height:2.5rem;border-radius:11px!important;background:transparent!important;color:var(--muted)!important;padding:0!important;border:0!important}
button[data-baseweb="tab"] p,[role="tab"] p{font-weight:600;font-size:.95rem;color:inherit!important}
button[data-baseweb="tab"][aria-selected="true"],[role="tab"][aria-selected="true"]{background:#fff!important;color:var(--ink)!important;box-shadow:0 1px 3px rgba(16,24,40,.14)}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"],.react-aria-SelectionIndicator{display:none!important}

.stButton,[data-testid="stButton"],[data-testid="stElementContainer"]:has([data-testid="stButton"]){width:100%!important}
[data-testid="stButton"] button,[data-testid="stFormSubmitButton"] button{width:100%!important;min-height:3rem;border-radius:14px;border:0;background:var(--cobalt);color:#fff}
[data-testid="stButton"] button p,[data-testid="stFormSubmitButton"] button p{color:#fff;font-weight:600;font-size:1rem}
[data-testid="stButton"] button:hover,[data-testid="stFormSubmitButton"] button:hover{background:#1E3AB5;color:#fff}
[data-testid="stButton"] button:focus-visible,[data-testid="stFormSubmitButton"] button:focus-visible{outline:3px solid #9DB0FF;outline-offset:2px}
div[data-baseweb="input"],div[data-baseweb="select"]>div,div[data-baseweb="textarea"]{border-radius:12px!important}
section[data-testid="stFileUploaderDropzone"]{border-radius:14px;border:1.5px dashed #B3BCDD;background:#fff}
[data-testid="stExpander"]{border:1px solid var(--line);border-radius:14px;background:#fff}
[data-testid="stCaptionContainer"]{color:var(--muted)}

.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:1rem;margin:1rem 0;box-shadow:0 1px 2px rgba(16,24,40,.04)}
.r-title{font-family:'Bricolage Grotesque','DM Sans',system-ui,sans-serif;font-weight:800;font-size:1.25rem;letter-spacing:-.015em;margin:0 0 .7rem}
.verdict{border-radius:14px;padding:.9rem 1rem}
.v-word{font-family:'Bricolage Grotesque','DM Sans',system-ui,sans-serif;font-weight:800;font-size:1.7rem;letter-spacing:-.02em;line-height:1.1}
.v-head{font-size:.95rem;margin-top:.3rem;line-height:1.35}
.v-no{background:#FDECEC;color:#8E1F1F}
.v-doubt{background:#FFF3DC;color:#7A4A00}
.v-ok{background:#E6F5EE;color:#0F5A3C}
.v-unk{background:#EDEFF6;color:#3C4768}
.sec{font-weight:700;font-size:.9rem;color:var(--muted);margin:1.1rem 0 .2rem}
.row{display:flex;gap:.7rem;padding:.7rem 0;border-top:1px solid var(--line)}
.row:first-of-type{border-top:0}
.chip{flex:none;align-self:flex-start;min-width:4.6rem;text-align:center;padding:.15rem .6rem;border-radius:999px;font-size:.75rem;font-weight:700}
.c-no{background:#C62F2F;color:#fff}
.c-doubt{background:#F2A93B;color:#3A2400}
.c-check{background:#E8EBF4;color:#3C4768}
.row b{display:block;font-size:1rem}
.why{color:var(--muted);font-size:.9rem;line-height:1.4}
.ask{margin:.3rem 0 0;padding-left:1.2rem}
.ask li{margin:.25rem 0;line-height:1.4;font-size:.95rem}
.fine{color:var(--muted);font-size:.82rem;margin-top:.7rem;line-height:1.4}
.foot{color:var(--muted);font-size:.8rem;line-height:1.45}

[data-testid="stButton"] button[kind="tertiary"],[data-testid="stButton"] button[data-testid="stBaseButton-tertiary"]{background:transparent!important;color:var(--cobalt)!important;min-height:2.2rem;width:auto!important;padding:0 .4rem}
[data-testid="stButton"] button[kind="tertiary"] p,[data-testid="stButton"] button[data-testid="stBaseButton-tertiary"] p{color:var(--cobalt)!important;font-weight:600;font-size:.9rem}
[data-testid="stForm"]{border:1px solid var(--line);border-radius:16px;background:#fff;padding:1rem}
.post{background:#fff;border:1px solid var(--line);border-radius:18px;padding:1rem;margin:.9rem 0 .2rem;box-shadow:0 1px 2px rgba(16,24,40,.04)}
.who{display:flex;align-items:center;gap:.6rem;margin-bottom:.6rem}
.avatar{flex:none;width:2.1rem;height:2.1rem;border-radius:50%;background:#E8EBF4;color:var(--cobalt);font-weight:700;display:flex;align-items:center;justify-content:center}
.who b{font-weight:700}
.muted{color:var(--muted);font-size:.85rem}
.bubble{background:var(--mist);border-radius:4px 16px 16px 16px;padding:.7rem .85rem;line-height:1.45;font-size:1rem}
.pills{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.7rem}
.pill{background:#E8EBF4;color:#3C4768;border-radius:999px;padding:.15rem .65rem;font-size:.8rem;font-weight:600}
.pill-amber{background:#FFE9BF;color:#6B4200}
.pill-green{background:#E6F5EE;color:#0F5A3C}
.ing{margin-top:.7rem;font-size:.9rem;line-height:1.4}
.done{margin-top:.7rem;font-weight:700;color:#0F5A3C}
.ended{margin-top:.7rem;font-weight:600;color:var(--muted)}
.title{font-family:'Bricolage Grotesque','DM Sans',system-ui,sans-serif;font-weight:800;font-size:1.2rem;letter-spacing:-.015em;margin:.1rem 0 .3rem}
.reply{background:var(--mist);border-radius:12px;padding:.45rem .7rem;margin:.3rem 0;font-size:.92rem;line-height:1.4}
.empty{color:var(--muted);text-align:center;padding:2rem 1rem;line-height:1.5}
.gate{background:#fff;border:1px solid var(--line);border-radius:18px;padding:1rem;margin:.4rem 0 1rem}
.gate p{margin:.2rem 0 .6rem}
@media (prefers-reduced-motion:no-preference){.card{animation:rise .25s ease-out}}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
</style>
"""


def header_html() -> str:
    return (
        f'<div class="brand">{LOGO_SVG}<span class="name">{NAME}</span></div>'
        f'<div class="hero">{esc(TAGLINE)}</div>'
        '<p class="sub">Share a plate, find a plate, and see what is happening around UChicago. '
        "Only for people with a uchicago.edu email.</p>"
    )


def _short_headline(text: str) -> str:
    for prefix in ("Not halal: found ", "Doubtful: "):
        if text.startswith(prefix):
            rest = text[len(prefix):]
            return ("Found " + rest) if prefix.startswith("Not") else rest[:1].upper() + rest[1:]
    return text


def result_html(analysis: rules.Analysis, title: str = "", warnings=()) -> str:
    parts = ['<div class="card">']
    if title:
        parts.append(f'<div class="r-title">{esc(title)}</div>')
    parts.append(
        f'<div class="verdict {VERDICT_CLASS[analysis.verdict]}">'
        f'<div class="v-word">{esc(VERDICT_WORD[analysis.verdict])}</div>'
        f'<div class="v-head">{esc(_short_headline(analysis.headline))}</div></div>'
    )
    flagged = [m for m in analysis.matches if m.status in CHIP]
    if flagged:
        parts.append('<div class="sec">What we found</div>')
        for m in flagged:
            word, css = CHIP[m.status]
            why = m.reason
            if m.note:
                why += " " + m.note
            if m.cleared:
                why += " The label says it is halal, so this is lower risk."
            parts.append(
                f'<div class="row"><span class="chip {css}">{word}</span>'
                f'<div><b>{esc(m.text)}</b><span class="why">{esc(why)}</span></div></div>'
            )
    if analysis.verify:
        parts.append('<div class="sec">Ask before you eat</div><ul class="ask">')
        parts.extend(f"<li>{esc(q)}</li>" for q in analysis.verify)
        parts.append("</ul>")
    for note in list(analysis.notes) + list(warnings):
        parts.append(f'<div class="fine">{esc(note)}</div>')
    parts.append("</div>")
    return "".join(parts)


def _plural(n: int) -> str:
    return f"{n} plate left" if n == 1 else f"{n} plates left"


def plate_card_html(p: dict, now: int) -> str:
    from ppl import copy
    from ppl.timefmt import ago_text, until_text

    nick = p["nickname"]
    body = esc(p["body"]).replace("\n", "<br>")
    pills = []
    if p["state"] == "open":
        pills.append(f'<span class="pill pill-amber">{esc(_plural(p["portions_left"]))}</span>')
    pills.append(f'<span class="pill">Pickup: {esc(p["place"])}</span>')
    pills.append(f'<span class="pill">{esc(until_text(p["when_ts"], now))}</span>')
    if p.get("tag") in copy.TAGS:
        pills.append(f'<span class="pill pill-green">{esc(copy.TAGS[p["tag"]])}</span>')
    parts = [
        '<div class="post">',
        f'<div class="who"><span class="avatar">{esc(nick[:1].upper())}</span>'
        f'<div><b>{esc(nick)}</b><br><span class="muted">{esc(ago_text(p["created_at"], now))}</span></div></div>',
        f'<div class="bubble">{body}</div>',
        f'<div class="pills">{"".join(pills)}</div>',
    ]
    if p.get("ingredients"):
        parts.append(f'<div class="ing"><b>Ingredients and allergens:</b> {esc(p["ingredients"])}</div>')
    if p["state"] == "shared":
        parts.append(f'<div class="done">{esc(copy.ALL_SHARED)}</div>')
    elif p["state"] == "ended":
        parts.append(f'<div class="ended">{esc(copy.ENDED)}</div>')
    parts.append("</div>")
    return "".join(parts)


def event_card_html(e: dict, now: int) -> str:
    from ppl.timefmt import event_when

    body = esc(e["body"]).replace("\n", "<br>")
    return (
        '<div class="post">'
        f'<div class="title">{esc(e["title"])}</div>'
        f'<div class="pills"><span class="pill pill-amber">{esc(event_when(e["when_ts"], now))}</span>'
        f'<span class="pill">{esc(e["place"])}</span></div>'
        f'<div class="bubble" style="margin-top:.7rem">{body}</div>'
        f'<div class="muted" style="margin-top:.6rem">Posted by {esc(e["nickname"])}</div>'
        "</div>"
    )
