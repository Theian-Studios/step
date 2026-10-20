#!/usr/bin/env python3
"""Build the STEP (Supporting Transitions to Employment Program) website into _site/.

    python3 build.py               # build for the live site
    python3 build.py --base /      # build for local preview at http://localhost:8080/

Sources:
    site.json                    site-wide settings (email, donate link, ...)
    content/participants/*.md    one file per participant story
    src/layout.html              shared <head>, header and footer
    src/pages/**.html            page bodies
    src/partials/*.html          snippets reused across pages
    src/templates/story.html     participant story page
    assets/                      CSS, JS and images (copied as-is)

How a build runs (see main()):
    1. Delete _site/ and copy assets/ into it.
    2. Read every participant file and make resized photos for each one.
    3. Fill a dictionary ("ctx") with every value a page can ask for: site settings,
       file hashes for cache-busting, ready-made HTML for cards and the carousel, ...
    4. For each page in src/pages/, swap its {{ placeholders }} for ctx values, then
       wrap it in src/layout.html. Same for one story page per participant.
    5. Write sitemap.xml, robots.txt and redirects for old addresses.

Templates are plain HTML with {{ name }} placeholders and nothing else: no loops or
conditions. Anything that repeats (cards, carousel slides) is built here in Python
and handed to the template as a finished HTML string. An unknown placeholder stops
the build with an error naming the file, so typos can't slip onto the live site.

Pillow is optional. When installed, photos are resized and converted to WebP
and social-sharing images are generated; without it, photos are copied as-is.
"""

import argparse
import datetime
import hashlib
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote, urlparse

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None

ROOT = Path(__file__).parent
OUT = ROOT / "_site"
IMG_SRC = ROOT / "assets" / "img"
IMG_OUT = OUT / "assets" / "img"

PLACEHOLDER = re.compile(r"\{\{\s*([\w.\-]+)\s*\}\}")


# --------------------------------------------------------------------------- helpers

def esc(text):
    """Make text safe to put inside HTML (turns < > & and quotes into entities)."""
    return html.escape(str(text), quote=True)


def render(template, ctx, source="template"):
    """Replace each {{ key }} in template with ctx[key]. `source` names the file in error messages."""
    def sub(match):
        key = match.group(1)
        if key not in ctx:
            raise KeyError(f"Unknown placeholder {{{{ {key} }}}} in {source}")
        return str(ctx[key])

    return PLACEHOLDER.sub(sub, template)


def split_front_matter(text, comment=False):
    """Return (meta, body) from '---' front matter (Markdown) or an HTML comment."""
    pattern = r"\A<!--\s*\n(.*?)\n-->\s*\n" if comment else r"\A---\s*\n(.*?)\n---\s*\n"
    match = re.match(pattern, text, re.S)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, text[match.end():]


def inline_md(text):
    return re.sub(r"\*(.+?)\*", r"<em>\1</em>", esc(text).replace("&#x27;", "’"))


def markdown_blocks(text):
    """Paragraphs separated by blank lines; '> ' is a pull quote, '## ' a heading."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = " ".join(line.strip() for line in block.splitlines())
        if block.startswith("> "):
            out.append(f'<p class="pull-quote">{inline_md(block[2:])}</p>')
        elif block.startswith("## "):
            out.append(f"<h2>{inline_md(block[3:])}</h2>")
        else:
            out.append(f"<p>{inline_md(block)}</p>")
    return "\n        ".join(out)


def first_paragraph(text):
    for block in re.split(r"\n\s*\n", text.strip()):
        if not block.startswith((">", "#")):
            return " ".join(block.split())
    return ""


def truncate(text, limit=155):
    text = re.sub(r"\*", "", text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


# --------------------------------------------------------------------------- images

class Photos:
    """Builds responsive versions of each participant photo."""

    WIDTHS = (480,)

    def __init__(self):
        self.info = {}

    def prepare(self, filename, position, og_name):
        if filename in self.info:
            return self.info[filename]
        src = IMG_SRC / filename
        stem = src.stem
        info = {"jpg": f"assets/img/{filename}", "webp": [], "size": None}
        if Image is not None:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                w, h = im.size
                info["size"] = (w, h)
                im.save(IMG_OUT / filename, "JPEG", quality=80, optimize=True, progressive=True)
                for width in [x for x in self.WIDTHS if x < w] + [w]:
                    name = f"{stem}-{width}.webp"
                    resized = im if width == w else im.resize((width, round(h * width / w)), Image.LANCZOS)
                    resized.save(IMG_OUT / name, "WEBP", quality=78, method=6)
                    info["webp"].append((name, width))
                self._og_image(im, position, og_name)
        self.info[filename] = info
        return info

    @staticmethod
    def _og_image(im, position, og_name):
        """1200x630 crop for link previews, keeping the face area."""
        w, h = im.size
        target = 1200 / 630
        y_pct = 0.3
        m = re.search(r"(\d+)%\s*$", position or "")
        if m:
            y_pct = int(m.group(1)) / 100
        crop_h = round(w / target)
        if crop_h <= h:
            top = round((h - crop_h) * y_pct)
            box = (0, top, w, top + crop_h)
        else:
            crop_w = round(h * target)
            left = (w - crop_w) // 2
            box = (left, 0, left + crop_w, h)
        (IMG_OUT / "og").mkdir(parents=True, exist_ok=True)
        im.crop(box).resize((1200, 630), Image.LANCZOS).save(
            IMG_OUT / "og" / og_name, "JPEG", quality=82, optimize=True, progressive=True
        )


def picture(base, info, alt, sizes, position="", eager=False):
    style = f' style="object-position:{esc(position)}"' if position else ""
    dims = f' width="{info["size"][0]}" height="{info["size"][1]}"' if info["size"] else ""
    loading = ' fetchpriority="high"' if eager else ' loading="lazy"'
    source = ""
    if info["webp"]:
        srcset = ", ".join(f"{base}assets/img/{name} {width}w" for name, width in info["webp"])
        source = f'<source type="image/webp" srcset="{srcset}" sizes="{sizes}">'
    return (
        f'<picture>{source}<img src="{base}{info["jpg"]}" alt="{esc(alt)}"{dims}'
        f'{loading} decoding="async"{style}></picture>'
    )


# How wide each kind of participant photo is drawn on screen. Browsers use this
# (the <img sizes> attribute) to download the smallest file that still looks sharp.
# Keep these roughly in line with styles.css if a layout changes.
SIZES = {
    "card": "(max-width: 600px) 100vw, (max-width: 960px) 50vw, 300px",   # cards on Home, Stories, story pages
    "hero": "(max-width: 900px) 100vw, 520px",                            # home page carousel
    "story": "(max-width: 960px) 100vw, 360px",                           # big photo on a story page
    "quote": "240px",                                                     # small round photo by quotes (About)
}


# --------------------------------------------------------------------------- participants

def load_participants(photos):
    """Read content/participants/*.md into a list of dicts, sorted by `order`."""
    people = []
    for path in sorted((ROOT / "content" / "participants").glob("*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        pid = path.stem
        if meta.get("draft", "no").lower() in ("yes", "true"):
            # draft: yes keeps the story in the repository but off the website.
            print(f"  {pid}: draft, not published")
            continue
        p = {
            "id": pid,
            "name": meta.get("name", pid.title()),
            "order": int(meta.get("order", 99)),
            "quote": meta.get("quote", ""),
            "card_quote": meta.get("card_quote") or meta.get("quote", ""),
            # The home page carousel can show a different quote from the cards.
            "hero_quote": meta.get("hero_quote") or meta.get("card_quote") or meta.get("quote", ""),
            "summary": meta.get("summary", ""),
            "position": meta.get("photo_position", "50% 30%"),
            "body_md": body,
            "photo_file": meta.get("photo", ""),
            "status": meta.get("status", ""),
            # Every *_quote setting (about_quote, how_quote, ...), so pages can quote this
            # person with {{ person.<id>.<setting> }} and the words live only in this file.
            "quotes": {k: v for k, v in meta.items() if k.endswith("quote")},
        }
        # Used for the page's search-engine description and link previews.
        p["excerpt"] = p["summary"] or first_paragraph(body)
        p["info"] = None  # photo details from Photos.prepare(), or None when there's no photo
        if p["photo_file"] and (IMG_SRC / p["photo_file"]).exists():
            p["info"] = photos.prepare(p["photo_file"], p["position"], f"{pid}.jpg")
        else:
            # No photo yet: cards and the story page show the person's initial instead.
            print(f"  {pid}: no photo yet, showing their initial")
        people.append(p)
    people.sort(key=lambda x: (x["order"], x["name"]))
    return people


def initial(p):
    """Stand-in for a missing photo: the person's first letter on light gray, in the same frame."""
    return f'<span class="photo-initial" aria-hidden="true">{esc(p["name"][:1].upper())}</span>'


def photo_for(p, base, variant):
    """The participant's photo as HTML for one of the SIZES variants (or their initial if no photo)."""
    if not p["info"]:
        return initial(p)
    # Photos near the top of a page load right away; the rest wait until scrolled near.
    eager = variant in ("hero", "story")
    return picture(base, p["info"], f"Portrait of {p['name']}", SIZES[variant], p["position"], eager)


def card(p, base, level=3, read=True):
    """A participant card linking to their story. `level` is the heading level for the name;
    `read` adds the small "Read story" button."""
    status = f'<span class="status-badge">{esc(p["status"])}</span>' if p["status"] else ""
    read_btn = (f'<span class="card__read">Read story<span class="visually-hidden"> about {esc(p["name"])}</span></span>'
                if read else "")
    return f"""<a class="card" href="{base}stories/{p['id']}.html">
        <div class="card__photo">{photo_for(p, base, 'card')}{status}</div>
        <h{level} class="card__name">{esc(p['name'])}</h{level}>
        <p class="card__quote">“{esc(p['card_quote'])}”</p>
        {read_btn}
      </a>"""


def carousel(people, base):
    """Hero carousel: one large portrait at a time; the quote card links to the story; dots switch people.
    Only people with a photo appear here."""
    slides, dots = [], []
    for i, p in enumerate([q for q in people if q["info"]]):
        active = " is-active" if i == 0 else ""
        url = f"{base}stories/{p['id']}.html"
        slides.append(
            f'<div class="hc__slide{active}" data-index="{i}"{"" if i == 0 else " aria-hidden=\"true\""}>'
            # Load every slide's photo up front so a slide never appears before its image.
            f'{picture(base, p["info"], f"Portrait of {p['name']}", SIZES["hero"], p["position"], eager=(i == 0)).replace(' loading="lazy"', '')}'
            f'<div class="hc__card"><p class="hc__quote">“{esc(p["hero_quote"])}”</p>'
            f'<div class="hc__meta"><span class="hc__name">{esc(p["name"])}</span>'
            f'<a class="hc__read" href="{url}"{"" if i == 0 else " tabindex=\"-1\""}>'
            f'Read story<span class="visually-hidden"> about {esc(p["name"])}</span></a></div></div></div>'
        )
        dots.append(
            f'<button class="hc__dot{active}" type="button" data-index="{i}" aria-label="Show {esc(p["name"])}"'
            f'{" aria-current=\"true\"" if i == 0 else ""}><span></span></button>'
        )
    return (
        '<div class="hc" aria-roledescription="carousel" aria-label="Participants">'
        f'<div class="hc__stage">{"".join(slides)}'
        '<button class="hc__nav hc__nav--prev" type="button" aria-label="Previous participant" hidden>'
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>'
        '<button class="hc__nav hc__nav--next" type="button" aria-label="Next participant" hidden>'
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg></button></div>'
        f'<div class="hc__dots" hidden>{"".join(dots)}</div></div>'
    )


def grid_cols(n):
    """Pick 3 or 4 columns so the last row of cards isn't a lone straggler."""
    if n <= 3:
        return "3"
    fill = lambda c: (n % c or c) / c  # how full the last row is
    return "4" if fill(4) >= fill(3) else "3"


# --------------------------------------------------------------------------- build

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="URL path the site is served from, e.g. / for local preview")
    args = parser.parse_args()

    site = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
    site_url = site["url"].rstrip("/") + "/"
    base = args.base if args.base is not None else (urlparse(site_url).path or "/")
    if not base.endswith("/"):
        base += "/"

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "assets", OUT / "assets", ignore=shutil.ignore_patterns(".DS_Store"))

    photos = Photos()
    people = load_participants(photos)

    donate = site["donate_url"]
    if not re.match(r"^(https?:|mailto:)", donate):
        donate = base + donate

    ctx = {
        "base": base,
        "year": datetime.date.today().year,
        "site.donate_url": esc(donate),
        **{f"site.{k}": esc(v) for k, v in site.items() if k != "donate_url" and isinstance(v, str)},
    }
    # Content hashes so browsers fetch new CSS/JS as soon as they change.
    for key, rel in (("css", "assets/css/styles.css"), ("js", "assets/js/main.js"),
                     ("logo", "assets/img/step-logo.svg"), ("logo_white", "assets/img/step-logo-white.svg"),
                     ("icon", "assets/img/logo-mark.svg"), ("favicon", "assets/img/favicon-32.png"),
                     ("touch_icon", "assets/img/apple-touch-icon.png"), ("og", "assets/img/og-home.jpg")):
        ctx[f"version.{key}"] = hashlib.sha1((ROOT / rel).read_bytes()).hexdigest()[:8]
    def site_link(href):
        """Links in site.json are written from the site root ("about.html"); add the base path."""
        if href == "donate":
            return donate
        if href.startswith("index.html#"):  # a section of the home page: link to "/#id", not "/index.html#id"
            return base + href[len("index.html"):]
        return href if re.match(r"^(https?:|mailto:|#)", href) else base + href

    # Partials are reusable snippets. The support band is filled per page (see support_band below).
    for path in (ROOT / "src" / "partials").glob("*.html"):
        if path.stem != "support":
            ctx[f"partial.{path.stem}"] = render(path.read_text(encoding="utf-8"), ctx, path.name)
    support_tpl = (ROOT / "src" / "partials" / "support.html").read_text(encoding="utf-8")

    def support_band(meta):
        """The blue "support" band. Wording and buttons come from site.json → support,
        and a page can override any of them with support_heading, support_text,
        support_button or support_button_2 in its settings. Buttons are written
        "Label | link"; "none" hides a button; the link "donate" means site.json's donate_url."""
        s = {key: meta.get(f"support_{key}", value) for key, value in site["support"].items()}
        buttons = []
        for key, style in (("button", "btn--light"), ("button_2", "btn--outline-light")):
            if s[key].strip().lower() in ("", "none"):
                continue
            label, _, href = (part.strip() for part in s[key].partition("|"))
            buttons.append(f'<a class="btn {style}" href="{esc(site_link(href))}">{esc(label)}</a>')
        return render(support_tpl, {
            "support.heading": esc(s["heading"]),
            "support.text": esc(s["text"]),
            "support.buttons": "\n      ".join(buttons),
        }, "support.html")

    def menu(current):
        """Header and footer menus from site.json → menu. `current` underlines the page you're on.
        An item with "header": false appears only in the footer, "footer": false only in the header,
        and "footer_label" renames it in the footer."""
        header, footer = [], []
        for item in site["menu"]:
            href = esc(site_link(item["href"]))
            here = ' aria-current="page"' if current and item.get("page") == current else ""
            if item.get("header", True):
                header.append(f'<a href="{href}"{here}>{esc(item["label"])}</a>')
            if item.get("footer", True):
                footer.append(f'<li><a href="{href}">{esc(item.get("footer_label", item["label"]))}</a></li>')
        return "\n        ".join(header), "\n            ".join(footer)

    # Ready-made participant HTML that pages drop in with {{ participants.* }}.
    # Home page cards skip the Read story button (the whole card is still a link).
    ctx["participants.all"] = "\n      ".join(card(p, base, read=False) for p in people)
    # The stories page has no section heading above the cards, so names are h2 there.
    ctx["participants.all_h2"] = "\n      ".join(card(p, base, level=2) for p in people)
    ctx["participants.carousel"] = carousel(people, base)
    ctx["participants.all_cols"] = grid_cols(len(people))
    # {{ photo.<id>.<variant> }}, e.g. {{ photo.jan.quote }} on the About page.
    for p in people:
        for variant in SIZES:
            ctx[f"photo.{p['id']}.{variant}"] = photo_for(p, base, variant)
    # {{ person.<id>.name }}, {{ person.<id>.url }}, {{ person.<id>.link }} ("Read Jan’s story")
    # and {{ person.<id>.<any *_quote setting> }}, so a page quoting someone always
    # matches their story file.
    for p in people:
        url = f"{base}stories/{p['id']}.html"
        ctx[f"person.{p['id']}.name"] = esc(p["name"])
        ctx[f"person.{p['id']}.url"] = url
        ctx[f"person.{p['id']}.link"] = f'<a href="{url}">Read {esc(p["name"])}’s story</a>'
        for key, text in p["quotes"].items():
            ctx[f"person.{p['id']}.{key}"] = inline_md(text)

    # Structured data (JSON-LD) so search engines can show the organization and stories properly.
    addr = site["postal_address"]
    org = {
        "@type": "NGO",
        "@id": site_url + "#organization",
        "name": site["name"],
        "alternateName": site["short_name"],
        "url": site_url,
        "logo": f"{site_url}assets/img/step-logo.svg",
        "email": site["email"],
        "description": site["tagline"] + ": paid, remote work and weekly training for people experiencing homelessness in Utah County.",
        "address": {"@type": "PostalAddress", "streetAddress": addr["street"], "addressLocality": addr["city"],
                    "addressRegion": addr["region"], "postalCode": addr["postal_code"], "addressCountry": addr["country"]},
        "areaServed": "Utah County, Utah",
        "parentOrganization": {"@type": "CollegeOrUniversity", "name": "Brigham Young University", "url": "https://www.byu.edu/"},
    }

    def jsonld(data):
        text = json.dumps({"@context": "https://schema.org", **data}, ensure_ascii=False, separators=(",", ":"))
        return '<script type="application/ld+json">' + text.replace("</", "<\\/") + "</script>"

    faq_item = re.compile(r'<details class="faq__item">\s*<summary>(.*?)</summary>\s*<div class="faq__answer">(.*?)</div>\s*</details>', re.S)

    def plain(fragment):
        return " ".join(html.unescape(re.sub(r"<[^>]+>", "", fragment)).split())

    def faq_jsonld(content):
        """FAQPage data for the question-and-answer blocks on a page, if it has any."""
        items = faq_item.findall(content)
        if not items:
            return None
        return {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": plain(q), "acceptedAnswer": {"@type": "Answer", "text": plain(a)}}
            for q, a in items]}

    layout = (ROOT / "src" / "layout.html").read_text(encoding="utf-8")
    default_og = f"{site_url}assets/img/og-home.jpg?v={ctx['version.og']}"
    sitemap = []

    def write_page(out_path, meta, content):
        url_path = out_path.replace("index.html", "")
        page_ctx = dict(ctx)
        page_ctx["nav.header"], page_ctx["nav.footer"] = menu(meta.get("current"))
        page_ctx["partial.support"] = support_band(meta)
        is_home = out_path == "index.html"
        title = meta["title"] if is_home else f"{meta['title']} | {site['short_name']}"
        page_ctx.update({
            "title": esc(title),
            "og_title": esc(meta.get("og_title", meta["title"])),
            "description": esc(meta["description"]),
            "canonical": esc(site_url + url_path),
            "og_type": meta.get("og_type", "website"),
            "og_image": esc(meta.get("og_image", default_og)),
            "og_image_alt": esc(meta.get("og_image_alt", site["name"])),
            "robots": '<meta name="robots" content="noindex">' if meta.get("noindex") else "",
        })
        page_ctx["content"] = render(content, page_ctx, out_path)
        data = meta.get("jsonld") or ([org] if is_home else [])
        data = [data] if isinstance(data, dict) else list(data)
        faq = faq_jsonld(page_ctx["content"])
        if faq:
            data.append(faq)
        page_ctx["jsonld"] = "\n  ".join(jsonld(d) for d in data)
        dest = OUT / out_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render(layout, page_ctx, "layout.html"), encoding="utf-8")
        if not meta.get("noindex"):
            sitemap.append(site_url + url_path)

    # Regular pages
    pages_dir = ROOT / "src" / "pages"
    for path in sorted(pages_dir.rglob("*.html")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"), comment=True)
        write_page(path.relative_to(pages_dir).as_posix(), meta, body)

    # Participant story pages
    story_tpl = (ROOT / "src" / "templates" / "story.html").read_text(encoding="utf-8")
    for i, p in enumerate(people):
        nxt = people[(i + 1) % len(people)]
        body = markdown_blocks(p["body_md"])
        if p["summary"]:
            # A summary opens the story as its first paragraph, like every other page.
            body = f'<p>{inline_md(p["summary"])}</p>\n        {body}'
        others = [q for q in people if q is not p][:4]
        story_ctx_cols = grid_cols(len(others))
        story_ctx = {
            "p.name": esc(p["name"]),
            "p.quote": esc(p["quote"]),
            "p.photo": photo_for(p, base, "story"),
            "p.body": body,
            "p.more": "\n      ".join(card(q, base) for q in others),
            "p.more_cols": story_ctx_cols,
            "p.url": esc(f"{site_url}stories/{p['id']}.html"),
            "p.share_url": quote(f"{site_url}stories/{p['id']}.html", safe=""),
            "p.next_url": f"{base}stories/{nxt['id']}.html",
            "p.next_name": esc(nxt["name"]),
            "p.next_quote": esc(nxt["card_quote"]),
            "p.status": f'<p class="status-badge status-badge--inline">{esc(p["status"])}</p>' if p["status"] else "",
        }
        meta = {
            "title": f"{p['name']}’s story",
            "og_title": f"Meet {p['name']}: “{p['quote']}”",
            "description": truncate(p["excerpt"]),
            "current": "stories",
            "og_type": "article",
        }
        if p["info"] and Image is not None:
            meta["og_image"] = f"{site_url}assets/img/og/{p['id']}.jpg"
            meta["og_image_alt"] = f"Portrait of {p['name']}"
        story_url = f"{site_url}stories/{p['id']}.html"
        publisher = {k: org[k] for k in ("@type", "@id", "name", "url", "logo")}
        meta["jsonld"] = [{
            "@type": "Article",
            "headline": meta["title"],
            "description": meta["description"],
            "url": story_url,
            "mainEntityOfPage": story_url,
            "image": meta.get("og_image", default_og),
            "about": {"@type": "Person", "name": p["name"]},
            "author": publisher,
            "publisher": publisher,
        }, {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": site_url},
                {"@type": "ListItem", "position": 2, "name": "Stories", "item": site_url + "stories/"},
                {"@type": "ListItem", "position": 3, "name": p["name"], "item": story_url},
            ],
        }]
        write_page(f"stories/{p['id']}.html", meta, render(story_tpl, {**ctx, **story_ctx}, "story.html"))

    # Old story links (story.html?p=jan) forward to the new pages.
    (OUT / "story.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Redirecting…</title>"
        f"<script>var p=new URLSearchParams(location.search).get('p');"
        f"location.replace('{base}stories/'+(p?encodeURIComponent(p)+'.html':''));</script>",
        encoding="utf-8",
    )
    (OUT / "stories.html").write_text(
        f'<!doctype html><meta charset=utf-8><meta http-equiv="refresh" content="0; url={base}stories/">'
        f'<link rel="canonical" href="{site_url}stories/"><title>Redirecting…</title>',
        encoding="utf-8",
    )

    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{esc(u)}</loc></url>\n" for u in sitemap)
        + "</urlset>\n",
        encoding="utf-8",
    )
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site_url}sitemap.xml\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Built {len(sitemap)} pages into {OUT.relative_to(ROOT)}/ (base {base})"
          + ("" if Image else " — Pillow not installed, images copied without resizing"))


if __name__ == "__main__":
    main()
