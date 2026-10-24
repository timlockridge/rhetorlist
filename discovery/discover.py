#!/usr/bin/env python3
"""
Rhetorlist book discovery.

Pulls recently published / recently deposited books from machine-readable
sources (Crossref, Parlor Press's Shopify product feed, Open Library, publisher
RSS), drops anything already in public/*.json, scores each title for relevance
to rhetoric & writing studies, and writes a review queue:

    discovery/candidates.json   - the live queue the book manager reads
    discovery/candidates.md     - the same queue as a readable report
    discovery/state.json        - last run time + every id already seen

Run it from the repo root:

    python3 discovery/discover.py            # normal weekly run
    python3 discovery/discover.py --dry-run  # fetch and report, write nothing
    python3 discovery/discover.py --classify # also ask Claude to judge relevance
    python3 discovery/discover.py --source parlor --source wac

Only the standard library is required. --classify needs `pip install anthropic`
and an ANTHROPIC_API_KEY (or `ant auth login`).

Every request identifies itself as this tool with a contact address, and the
script makes at most one ordinary page view per shortlisted candidate.
"""

import argparse
import datetime as dt
import difflib
import glob
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, "public")
SOURCES_PATH = os.path.join(HERE, "sources.json")
STATE_PATH = os.path.join(HERE, "state.json")
CANDIDATES_JSON = os.path.join(HERE, "candidates.json")
CANDIDATES_MD = os.path.join(HERE, "candidates.md")

CONTACT_EMAIL = "timlockridge@gmail.com"
USER_AGENT = f"rhetorlist-discovery/1.0 (+https://rhetorlist.net; mailto:{CONTACT_EMAIL})"

TODAY = dt.date.today()


# ----------------------------------------------------------------------------
# small utilities
# ----------------------------------------------------------------------------

def log(msg):
    print(msg, file=sys.stderr, flush=True)


def http_get(url, accept="application/json, text/xml, */*", retries=3, timeout=40):
    """GET with polite retry on 429/5xx. Returns the body as text, or None."""
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                wait = 3 + 5 * attempt
                retry_after = e.headers.get("Retry-After") if e.headers else None
                if retry_after and retry_after.isdigit():
                    wait = max(wait, min(int(retry_after), 60))
                log(f"    {e.code} from {url[:80]} - retrying in {wait}s")
                time.sleep(wait)
                continue
            log(f"    HTTP {e.code} for {url[:100]}")
            return None
        except Exception as e:  # network, timeout, decode
            last = e
            time.sleep(1 + attempt)
    log(f"    giving up on {url[:100]}: {last}")
    return None


def http_json(url, **kw):
    text = http_get(url, **kw)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log(f"    non-JSON response from {url[:100]}")
        return None


def clean_text(text):
    """Decode HTML entities (Crossref double-encodes: '&amp;#x3a;') and trim."""
    text = html.unescape(html.unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def normalize(text):
    """Lowercase, strip punctuation and leading articles for title matching."""
    text = html.unescape(text or "").lower()
    text = text.replace("&", "and")
    text = re.sub(r"[\u2018\u2019\u201c\u201d'\"]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(the|a|an)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def main_title(title):
    return re.split(r"[:\u2014\u2013]|\s-\s", title or "", maxsplit=1)[0]


def surname(author_string):
    """Last word of the first listed author."""
    first = re.split(r",| and ", author_string or "")[0].strip()
    parts = first.split()
    return normalize(parts[-1]) if parts else ""


def format_authors(people):
    """['Ada Lovelace', 'Grace Hopper', 'X'] -> 'Ada Lovelace, Grace Hopper, and X'."""
    people = [p for p in people if p]
    if not people:
        return ""
    if len(people) == 1:
        return people[0]
    if len(people) == 2:
        return f"{people[0]} and {people[1]}"
    return ", ".join(people[:-1]) + ", and " + people[-1]


def strip_html(fragment):
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment or "", flags=re.S | re.I)
    text = re.sub(r"</(p|div|br|li|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in text.split("\n")]
    return [p for p in paragraphs if len(p) > 40]


# ----------------------------------------------------------------------------
# existing catalogue
# ----------------------------------------------------------------------------

def load_existing():
    books = []
    for path in sorted(glob.glob(os.path.join(PUBLIC, "20[0-9][0-9].json"))):
        try:
            with open(path, encoding="utf-8") as f:
                books.extend(json.load(f))
        except Exception as e:
            log(f"could not read {path}: {e}")
    index = {"full": {}, "main": {}, "urls": set()}
    for b in books:
        full = normalize(b.get("title", ""))
        main = normalize(main_title(b.get("title", "")))
        if full:
            index["full"][full] = b
        if main:
            index["main"].setdefault(main, []).append(b)
        if b.get("publisherURL"):
            index["urls"].add(b["publisherURL"].rstrip("/").lower())
    return books, index


def already_listed(cand, index):
    """Return the matching existing book, or None."""
    full = normalize(cand["title"])
    if full in index["full"]:
        return index["full"][full]
    main = normalize(main_title(cand["title"]))
    cand_surname = surname(cand.get("author", ""))
    for b in index["main"].get(main, []):
        if not cand_surname or cand_surname in normalize(b.get("author", "")):
            return b
    # fuzzy fallback: near-identical full titles (typos, punctuation variants)
    if len(full) > 25:
        for existing_full, b in index["full"].items():
            if abs(len(existing_full) - len(full)) < 6 and \
                    difflib.SequenceMatcher(None, full, existing_full).ratio() > 0.94:
                return b
    if cand.get("url") and cand["url"].rstrip("/").lower() in index["urls"]:
        return {"title": cand["title"], "author": cand.get("author", "")}
    return None


# ----------------------------------------------------------------------------
# relevance
# ----------------------------------------------------------------------------

class Relevance:
    def __init__(self, cfg):
        self.strong = [k.lower() for k in cfg.get("strong", [])]
        self.medium = [k.lower() for k in cfg.get("medium", [])]
        self.negative = [k.lower() for k in cfg.get("negative", [])]
        self.likely = cfg.get("likely_threshold", 3)
        self.possible = cfg.get("possible_threshold", 1)

    @staticmethod
    def _hits(text, keywords):
        return [k for k in keywords if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", text)]

    def score(self, cand):
        title_text = normalize(cand["title"])
        body_text = normalize(" ".join([
            cand.get("series") or "",
            " ".join(cand.get("tags") or []),
            " ".join(cand.get("description") or [])[:1500],
        ]))
        score = 0
        reasons = []
        for k in self._hits(title_text, self.strong):
            score += 3
            reasons.append(f"+3 title:{k}")
        for k in self._hits(title_text, self.medium):
            score += 1
            reasons.append(f"+1 title:{k}")
        for k in self._hits(body_text, self.strong):
            score += 2
            reasons.append(f"+2 text:{k}")
        for k in self._hits(body_text, self.medium)[:3]:
            score += 1
            reasons.append(f"+1 text:{k}")
        for k in self._hits(title_text + " " + body_text, self.negative):
            score -= 3
            reasons.append(f"-3 {k}")
        return score, reasons

    def bucket(self, score, always_relevant=False):
        if always_relevant:
            # a publisher that is in-field by default, unless a negative keyword
            # (poetry, fiction ...) fired
            return "likely" if score > -3 else "possible"
        if score >= self.likely:
            return "likely"
        if score >= self.possible:
            return "possible"
        return "unlikely"


# ----------------------------------------------------------------------------
# candidate shape
# ----------------------------------------------------------------------------

def make_candidate(**kw):
    cand = {
        "id": "",
        "source": "",
        "sourceType": "",
        "title": "",
        "author": "",
        "publisher": "",
        "publicationDate": "",      # ISO, as precise as the source gives
        "isbn": "",
        "doi": "",
        "url": "",                  # best known landing page
        "searchURL": "",            # publisher site search for the title
        "coverURL": "",
        "openAccess": "",           # 'yes' / 'no' / '' (unknown)
        "description": [],
        "series": "",
        "tags": [],
        "score": 0,
        "scoreReasons": [],
        "bucket": "",
        "llm": None,
        "status": "new",            # new -> added | dismissed (set by the book manager)
        "firstSeen": TODAY.isoformat(),
    }
    cand.update(kw)
    return cand


def apply_label(src, publisher_field, series="", extra_text=""):
    label = src.get("label", publisher_field)
    for rule in src.get("label_rules", []):
        field = rule.get("field", "publisher")
        haystack = {
            "publisher": publisher_field,
            "series": series,
            "any": " ".join([publisher_field, series, extra_text]),
        }.get(field, publisher_field)
        if re.search(rule["match"], haystack or "", re.I):
            label = rule["label"]
            break
    return label


def search_url(src, title, publisher=""):
    tpl = src.get("search_url")
    if not tpl:
        return ""
    return (tpl.replace("{title}", urllib.parse.quote_plus(main_title(title)))
               .replace("{publisher}", urllib.parse.quote_plus(publisher)))


# ----------------------------------------------------------------------------
# source: Crossref
# ----------------------------------------------------------------------------

CROSSREF_SELECT = "DOI,title,subtitle,author,editor,publisher,ISBN,issued,created,URL,abstract,container-title,type"


def crossref_date(item):
    for key in ("issued", "published-print", "published-online", "published"):
        parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
        if parts and parts[0]:
            return "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts))
    return ""


def crossref_people(item):
    people = item.get("author") or item.get("editor") or []
    names = []
    for p in people:
        if p.get("name"):
            names.append(p["name"])
        else:
            names.append(" ".join(x for x in [p.get("given"), p.get("family")] if x))
    names = [clean_text(n) for n in names]
    # some deposits list the press itself as a contributor
    people_only = [n for n in names if not re.search(r"\b(press|university|publishing|publishers)\b", n, re.I)]
    return format_authors(people_only or names)


def crossref_to_candidate(item, src):
    title = clean_text((item.get("title") or [""])[0])
    subtitle = clean_text((item.get("subtitle") or [""])[0])
    if subtitle and normalize(subtitle) not in normalize(title):
        title = f"{title}: {subtitle}"
    if not title:
        return None
    series = clean_text((item.get("container-title") or [""])[0])
    publisher_field = clean_text(item.get("publisher", ""))
    abstract = strip_html(item.get("abstract", "")) if item.get("abstract") else []
    label = apply_label(src, publisher_field, series, " ".join(abstract)[:500])
    isbn = (item.get("ISBN") or [""])[0]
    return make_candidate(
        id=f"doi:{item['DOI'].lower()}",
        source=src["id"], sourceType="crossref",
        title=title, author=crossref_people(item), publisher=label,
        publicationDate=crossref_date(item), isbn=isbn, doi=item["DOI"],
        url=item.get("URL") or f"https://doi.org/{item['DOI']}",
        searchURL=search_url(src, title, label),
        openAccess=src.get("open_access", ""),
        description=abstract, series=series, tags=[],
        crossrefPublisher=publisher_field,
    )


def crossref_query(params):
    params = dict(params)
    params["mailto"] = CONTACT_EMAIL
    return http_json("https://api.crossref.org/works?" + urllib.parse.urlencode(params))


def fetch_crossref(src, since_pub, since_created, keyword_queries):
    base_filter = (f"member:{src['member']},type:monograph,type:book,type:edited-book,"
                   f"from-pub-date:{since_pub},from-created-date:{since_created}")
    found = {}
    if src.get("mode", "all") == "all":
        cursor = "*"
        pages = 0
        while cursor and pages < 20:
            data = crossref_query({"filter": base_filter, "rows": 1000, "cursor": cursor,
                                   "select": CROSSREF_SELECT})
            if not data:
                break
            msg = data["message"]
            for item in msg.get("items", []):
                found[item["DOI"]] = item
            pages += 1
            if len(msg.get("items", [])) < 1000:
                break
            cursor = msg.get("next-cursor")
            time.sleep(1)
    else:
        for q in keyword_queries:
            data = crossref_query({"query.bibliographic": q, "filter": base_filter,
                                   "rows": 100, "select": CROSSREF_SELECT})
            if data:
                for item in data["message"].get("items", []):
                    found[item["DOI"]] = item
            time.sleep(1)

    pm = src.get("publisher_match")
    out = []
    for item in found.values():
        if pm and not re.search(pm, item.get("publisher", ""), re.I):
            continue
        cand = crossref_to_candidate(item, src)
        if cand:
            # keyword searches at big publishers return loosely related titles;
            # those must earn their place from the title itself
            cand["titleMustMatch"] = src.get("mode", "all") == "keywords"
            out.append(cand)
    return out


# ----------------------------------------------------------------------------
# source: Shopify storefront JSON (Parlor Press)
# ----------------------------------------------------------------------------

def shopify_product_candidate(src, base, p, skip_tags):
    """Build a candidate from one Shopify product record (products.json shape)."""
    if (p.get("product_type") or "").lower() not in ("book", "books", ""):
        return None
    tags = list(p.get("tags") or [])
    if any(t.lower() in skip_tags for t in tags):
        return None
    published = (p.get("published_at") or p.get("created_at") or "")[:10]
    return make_candidate(
        id=f"shopify:{base}:{p['handle']}",
        source=src["id"], sourceType="shopify",
        title=clean_text(p["title"]),
        author=clean_text(p.get("vendor") or ""),
        publisher=src["label"],
        publicationDate=published,
        url=f"{base}/products/{p['handle']}",
        coverURL=(p.get("images") or [{}])[0].get("src", ""),
        openAccess="yes" if any("open access" in t.lower() for t in tags) else "no",
        description=strip_html(p.get("body_html", "")),
        series=next((t for t in tags if "series" in t.lower() or "studies in" in t.lower()), ""),
        tags=tags,
    )


def fetch_shopify(src, since_pub, state):
    """Parlor Press runs on Shopify. The storefront's /products.json gives full
    metadata but is rate limited per IP, so the primary route is the product
    sitemap (meant for crawlers: every product handle, title and cover image).
    New handles get one /products/<handle>.json request each for author, date
    and description; if that is throttled the candidate still appears with what
    the sitemap knows and a link to the page.

    The first run only records the current handles as a baseline (the store's
    whole backlist would otherwise flood the queue); later runs surface new ones."""
    base = src["base_url"].rstrip("/")
    skip_tags = [t.lower() for t in src.get("skip_tags", [])]
    seen = state.setdefault("seen", {})

    sitemap = http_get(f"{base}/sitemap_products_1.xml?from=1&to=99999999999",
                       accept="application/xml, text/xml, */*", retries=2)
    if not sitemap:
        log("    product sitemap unavailable")
        return []
    products = []
    for block in re.findall(r"<url>(.*?)</url>", sitemap, re.S):
        loc = re.search(r"<loc>(.*?)</loc>", block)
        if not loc or "/products/" not in loc.group(1):
            continue
        handle = loc.group(1).rstrip("/").rsplit("/", 1)[-1]
        title = re.search(r"<image:title>(.*?)</image:title>", block, re.S)
        image = re.search(r"<image:loc>(.*?)</image:loc>", block, re.S)
        products.append({
            "handle": handle,
            "title": clean_text(title.group(1)) if title else handle.replace("-", " ").title(),
            "image": html.unescape(image.group(1)) if image else "",
        })
    log(f"    sitemap lists {len(products)} products")

    baseline_key = f"shopifyBaseline:{base}"
    if not state.get(baseline_key):
        for p in products:
            seen.setdefault(f"shopify:{base}:{p['handle']}", "baseline")
        state[baseline_key] = TODAY.isoformat()
        log(f"    first run: recorded {len(products)} existing products as the baseline; "
            f"new titles will show up from the next run")
        return []

    new_products = [p for p in products if f"shopify:{base}:{p['handle']}" not in seen]
    log(f"    {len(new_products)} products not seen before")
    out = []
    throttled = 0
    for p in new_products:
        cand = None
        if throttled < 2:
            data = http_json(f"{base}/products/{p['handle']}.json", retries=1)
            if data and data.get("product"):
                cand = shopify_product_candidate(src, base, data["product"], skip_tags)
                if cand is None:
                    seen[f"shopify:{base}:{p['handle']}"] = "unlikely"  # poetry etc., or not a book
                    continue
                if cand["publicationDate"] and cand["publicationDate"] < since_pub:
                    seen[f"shopify:{base}:{p['handle']}"] = "listed"
                    continue
            else:
                throttled += 1
            time.sleep(5)
        if cand is None:
            cand = make_candidate(
                id=f"shopify:{base}:{p['handle']}", source=src["id"], sourceType="shopify",
                title=p["title"], publisher=src["label"], url=f"{base}/products/{p['handle']}",
                coverURL=p["image"], openAccess="",
                note="Store metadata was throttled; open the page for author, date and description.",
            )
        out.append(cand)
    return out


# ----------------------------------------------------------------------------
# source: Open Library
# ----------------------------------------------------------------------------

def parse_ol_date(text, year):
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%B %Y", "%b %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return str(year)


def fetch_openlibrary(src, since_pub):
    since_year = int(since_pub[:4])
    params = urllib.parse.urlencode({
        "publisher": src["publisher"], "sort": "new", "limit": 100,
        "fields": "key,title,subtitle,author_name,first_publish_year,publish_date,isbn,publisher,cover_i",
    })
    data = http_json("https://openlibrary.org/search.json?" + params)
    out = []
    for doc in (data or {}).get("docs", []):
        year = doc.get("first_publish_year")
        if not year or year < since_year:
            continue
        title = doc.get("title", "").strip()
        if doc.get("subtitle"):
            title = f"{title}: {doc['subtitle'].strip()}"
        iso = str(year)
        for d in doc.get("publish_date", []):
            if str(year) in d:
                iso = parse_ol_date(d, year)
                if len(iso) == 10:
                    break
        isbn = next((i for i in doc.get("isbn", []) if len(i) == 13), (doc.get("isbn") or [""])[0])
        out.append(make_candidate(
            id=f"ol:{doc['key']}",
            source=src["id"], sourceType="openlibrary",
            title=title, author=format_authors(doc.get("author_name", [])),
            publisher=src["label"], publicationDate=iso, isbn=isbn,
            url=f"https://openlibrary.org{doc['key']}",
            searchURL=search_url(src, title, src["label"]),
            coverURL=f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg" if doc.get("cover_i") else "",
            openAccess=src.get("open_access", ""),
        ))
    return out


# ----------------------------------------------------------------------------
# source: RSS (publisher news - reported separately, not as book candidates)
# ----------------------------------------------------------------------------

def fetch_rss(src):
    raw = http_get(src["url"], accept="application/rss+xml, application/atom+xml, text/xml, */*")
    if not raw:
        return []
    try:
        root = ET.fromstring(raw.encode("utf-8"))
    except ET.ParseError:
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for node in root.iter("item"):
        items.append({
            "title": html.unescape((node.findtext("title") or "").strip()),
            "link": (node.findtext("link") or "").strip(),
            "date": (node.findtext("pubDate") or "").strip(),
            "summary": " ".join(strip_html(node.findtext("description") or ""))[:300],
        })
    for node in root.findall("atom:entry", ns):
        link = node.find("atom:link", ns)
        items.append({
            "title": html.unescape((node.findtext("atom:title", default="", namespaces=ns) or "").strip()),
            "link": link.get("href") if link is not None else "",
            "date": (node.findtext("atom:updated", default="", namespaces=ns) or "").strip(),
            "summary": " ".join(strip_html(node.findtext("atom:summary", default="", namespaces=ns) or ""))[:300],
        })
    for it in items:
        it["source"] = src["id"]
        it["publisher"] = src["label"]
    return items


# ----------------------------------------------------------------------------
# enrichment: one ordinary page view per shortlisted candidate
# ----------------------------------------------------------------------------

def meta_content(page, prop):
    for pattern in (
        r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\']',
    ):
        m = re.search(pattern, page, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def enrich(cand):
    """Follow the candidate's URL (usually a DOI) and pick up description/cover/landing page."""
    if not cand.get("url"):
        return
    req = urllib.request.Request(cand["url"], headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            final = resp.geturl()
            page = resp.read(600000).decode("utf-8", "ignore")
    except Exception as e:
        cand["enrichError"] = str(e)[:120]
        return
    if "chooser.crossref.org" in final:
        return
    cand["landingURL"] = final
    if not cand.get("description"):
        desc = meta_content(page, "og:description") or meta_content(page, "description")
        if desc and len(desc) > 60 and not desc.lower().startswith("choose from"):
            cand["description"] = [desc]
    if not cand.get("coverURL"):
        img = meta_content(page, "og:image")
        if img and re.search(r"\.(jpe?g|png|webp)(\?|$)", img, re.I) and "logo" not in img.lower():
            cand["coverURL"] = urllib.parse.urljoin(final, img)


# ----------------------------------------------------------------------------
# optional: ask Claude to judge relevance
# ----------------------------------------------------------------------------

def classify_with_claude(cands, model="claude-opus-5-5"):
    try:
        import anthropic
    except ImportError:
        log("--classify needs the anthropic package: pip install anthropic")
        return
    client = anthropic.Anthropic()
    system = (
        "You help maintain Rhetorlist, a list of new scholarly books in rhetoric and writing studies: "
        "rhetoric (classical through digital), composition studies, writing program administration, "
        "writing centers, literacy studies, technical and professional communication, and closely "
        "related work in English studies. Trade books, textbooks for general audiences, poetry, fiction, "
        "and books from other disciplines that merely use the word 'rhetoric' loosely do not belong. "
        "Judge each book from its metadata. Respond with only a JSON array of objects with keys "
        "\"id\", \"in_field\" (true/false) and \"reason\" (under 15 words)."
    )
    for start in range(0, len(cands), 40):
        batch = cands[start:start + 40]
        payload = [{
            "id": c["id"], "title": c["title"], "author": c["author"], "publisher": c["publisher"],
            "series": c.get("series", ""), "tags": c.get("tags", [])[:8],
            "description": " ".join(c.get("description", []))[:600],
        } for c in batch]
        try:
            response = client.messages.create(
                model=model, max_tokens=16000,
                output_config={"effort": "low"},
                system=system,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
        except anthropic.APIStatusError as e:
            log(f"    Claude API error {e.status_code}: {e.message}")
            return
        if response.stop_reason == "refusal":
            log("    Claude declined the classification request")
            return
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            log("    could not parse classification response")
            continue
        try:
            verdicts = {v["id"]: v for v in json.loads(m.group(0))}
        except (json.JSONDecodeError, KeyError, TypeError):
            log("    could not parse classification JSON")
            continue
        for c in batch:
            v = verdicts.get(c["id"])
            if not v:
                continue
            c["llm"] = {"inField": bool(v.get("in_field")), "reason": v.get("reason", "")}
            if c["llm"]["inField"] and c["bucket"] != "likely":
                c["bucket"] = "likely"
            elif not c["llm"]["inField"] and c["bucket"] == "likely" and not c.get("alwaysRelevant"):
                c["bucket"] = "possible"


# ----------------------------------------------------------------------------
# report
# ----------------------------------------------------------------------------

def md_escape(s):
    return (s or "").replace("|", "\\|").replace("\n", " ")


def write_markdown(queue, news, manual_checks, stats, path):
    lines = ["# Rhetorlist discovery report", "",
             f"Run: {dt.datetime.now():%Y-%m-%d %H:%M}. "
             f"Fetched {stats['fetched']} records from {stats['sources']} sources; "
             f"{stats['already']} already listed, {stats['new']} new this run, "
             f"{stats['pending']} pending review in total.", "",
             "Open the book manager (`npm start`, then http://localhost:4000/book-manager.html) "
             "and use **Review Candidates** to add or dismiss each one. "
             "Rows marked NEW appeared for the first time in this run.", ""]
    pending = [c for c in queue if c["status"] == "new"]
    sections = (("likely", "Likely in field"), ("possible", "Possibly in field"),
                ("unlikely", "Probably not in field (titles only)"))
    for bucket, heading in sections:
        rows = [c for c in pending if c["bucket"] == bucket]
        if not rows:
            continue
        lines += [f"## {heading} ({len(rows)})", ""]
        if bucket == "unlikely":
            by_pub = {}
            for c in rows:
                by_pub.setdefault(c["publisher"], []).append(c)
            for pub in sorted(by_pub):
                titles = "; ".join(
                    f"{'**NEW** ' if c['firstSeen'] == TODAY.isoformat() else ''}{md_escape(c['title'])}"
                    for c in sorted(by_pub[pub], key=lambda c: c["title"]))
                lines.append(f"- **{md_escape(pub)}** ({len(by_pub[pub])}): {titles}")
            lines.append("")
            continue
        lines += ["| | Title | Author | Publisher | Date | Links | Why |", "|---|---|---|---|---|---|---|"]
        for c in sorted(rows, key=lambda c: (c["publisher"], c["publicationDate"])):
            links = []
            if c.get("landingURL") or c.get("url"):
                links.append(f"[page]({c.get('landingURL') or c['url']})")
            if c.get("searchURL"):
                links.append(f"[search]({c['searchURL']})")
            why = ", ".join(c.get("scoreReasons", [])[:3])
            if c.get("llm"):
                why = f"Claude: {'yes' if c['llm']['inField'] else 'no'} - {c['llm']['reason']}; " + why
            flag = "**NEW**" if c["firstSeen"] == TODAY.isoformat() else ""
            lines.append(f"| {flag} | {md_escape(c['title'])} | {md_escape(c['author'])} | "
                         f"{md_escape(c['publisher'])} | {c['publicationDate']} | {' '.join(links)} | {md_escape(why)} |")
        lines.append("")
    if news:
        lines += ["## Publisher news mentioning the field", ""]
        for n in news:
            lines.append(f"- {md_escape(n['publisher'])}: [{md_escape(n['title'])}]({n['link']}) {n['date'][:16]}")
        lines.append("")
    if manual_checks:
        lines += ["## Still worth a manual look", "",
                  "These sources publish no machine-readable list of new titles.", ""]
        for m in manual_checks:
            lines.append(f"- [{md_escape(m['label'])}]({m['url']})")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", help="only run these source ids (repeatable)")
    ap.add_argument("--since", help="earliest publication date to consider, YYYY-MM-DD (default: Jan 1 of last year)")
    ap.add_argument("--created-since", help="earliest Crossref deposit date, YYYY-MM-DD "
                                            "(default: last run minus 7 days, or 120 days ago)")
    ap.add_argument("--no-enrich", action="store_true", help="skip fetching landing pages for descriptions and covers")
    ap.add_argument("--enrich-limit", type=int, default=60, help="at most this many landing pages per run (default 60)")
    ap.add_argument("--classify", action="store_true", help="ask Claude to judge relevance of likely/possible candidates")
    ap.add_argument("--dry-run", action="store_true", help="fetch and print the report, but write nothing")
    ap.add_argument("--include-unlikely", action="store_true", help="keep 'unlikely' titles in candidates.json too")
    args = ap.parse_args()

    cfg = load_json(SOURCES_PATH, None)
    if not cfg:
        sys.exit(f"cannot read {SOURCES_PATH}")
    state = load_json(STATE_PATH, {"lastRun": None, "seen": {}})
    queue = load_json(CANDIDATES_JSON, [])
    queue_by_id = {c["id"]: c for c in queue}

    since_pub = args.since or f"{TODAY.year - 1}-01-01"
    if args.created_since:
        since_created = args.created_since
    elif state.get("lastRun"):
        since_created = (dt.date.fromisoformat(state["lastRun"][:10]) - dt.timedelta(days=7)).isoformat()
    else:
        since_created = (TODAY - dt.timedelta(days=120)).isoformat()
    log(f"publication window from {since_pub}; Crossref deposits since {since_created}")

    _, index = load_existing()
    relevance = Relevance(cfg.get("relevance", {}))
    keyword_queries = cfg.get("keyword_queries", [])

    fetched = []
    news = []
    sources_run = 0
    for src in cfg["sources"]:
        if args.source and src["id"] not in args.source:
            continue
        sources_run += 1
        log(f"[{src['id']}] {src['type']} ...")
        try:
            if src["type"] == "crossref":
                items = fetch_crossref(src, since_pub, since_created, keyword_queries)
            elif src["type"] == "shopify":
                items = fetch_shopify(src, since_pub, state)
            elif src["type"] == "openlibrary":
                items = fetch_openlibrary(src, since_pub)
            elif src["type"] == "rss":
                rss_items = fetch_rss(src)
                relevant = 0
                for it in rss_items:
                    score, _ = relevance.score({"title": it["title"], "description": [it["summary"]]})
                    if score >= relevance.possible:
                        news.append(it)
                        relevant += 1
                log(f"    {len(rss_items)} news items, {relevant} relevant")
                continue
            else:
                log(f"    unknown source type {src['type']}")
                continue
        except Exception as e:
            log(f"    failed: {e}")
            continue
        for c in items:
            c["alwaysRelevant"] = bool(src.get("always_relevant"))
        log(f"    {len(items)} records")
        fetched.extend(items)

    # de-duplicate within this run (same book from two sources)
    by_key = {}
    for c in fetched:
        # hardcover and ebook editions carry different DOIs/ISBNs: key on the book itself
        key = normalize(c["title"]) + "|" + surname(c["author"])
        if key in by_key:
            keep = by_key[key]
            for field in ("description", "coverURL", "openAccess", "isbn", "doi"):
                if not keep.get(field) and c.get(field):
                    keep[field] = c[field]
            continue
        by_key[key] = c
    fetched = list(by_key.values())

    already = 0
    new_this_run = []
    for c in fetched:
        if state["seen"].get(c["id"]) in ("added", "dismissed", "listed", "unlikely"):
            continue
        if c["id"] in queue_by_id:
            continue  # already pending review
        if already_listed(c, index):
            already += 1
            state["seen"][c["id"]] = "listed"
            continue
        score, reasons = relevance.score(c)
        c["score"], c["scoreReasons"] = score, reasons
        c["bucket"] = relevance.bucket(score, c.get("alwaysRelevant"))
        if c.get("titleMustMatch") and not any(r.startswith("+3 title:") for r in reasons):
            c["bucket"] = "unlikely"
        new_this_run.append(c)

    shortlisted = [c for c in new_this_run if c["bucket"] in ("likely", "possible")]
    if not args.no_enrich and shortlisted:
        # one page view each, likely titles only, newest first, capped so a run stays short
        to_enrich = sorted((c for c in shortlisted if c["sourceType"] == "crossref" and c["bucket"] == "likely"),
                           key=lambda c: c["publicationDate"], reverse=True)[:args.enrich_limit]
        log(f"enriching {len(to_enrich)} likely candidates (one page view each) ...")
        for i, c in enumerate(to_enrich, 1):
            enrich(c)
            if i % 10 == 0:
                log(f"    {i}/{len(to_enrich)}")
            time.sleep(1)
    if args.classify and shortlisted:
        log(f"asking Claude about {len(shortlisted)} candidates ...")
        classify_with_claude(shortlisted)

    for c in new_this_run:
        if c["bucket"] == "unlikely" and not args.include_unlikely:
            state["seen"][c["id"]] = "unlikely"
        else:
            state["seen"][c["id"]] = "candidate"
            queue.append(c)

    # unlikely titles still go in the markdown so they can be eyeballed once
    report_queue = queue + [c for c in new_this_run if c["bucket"] == "unlikely" and not args.include_unlikely]
    stats = {
        "fetched": len(fetched), "sources": sources_run, "already": already,
        "new": len(new_this_run), "pending": sum(1 for c in queue if c["status"] == "new"),
    }
    counts = {b: sum(1 for c in new_this_run if c["bucket"] == b) for b in ("likely", "possible", "unlikely")}
    log(f"fetched {stats['fetched']}, already listed {already}, new {stats['new']} "
        f"(likely {counts['likely']}, possible {counts['possible']}, unlikely {counts['unlikely']}); "
        f"pending {stats['pending']}")

    if args.dry_run:
        write_markdown(report_queue, news, cfg.get("manual_checks", []), stats, "/dev/stdout")
        return

    state["lastRun"] = dt.datetime.now().isoformat(timespec="seconds")
    state["lastStats"] = stats
    with open(CANDIDATES_JSON, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    write_markdown(report_queue, news, cfg.get("manual_checks", []), stats, CANDIDATES_MD)
    log(f"wrote {os.path.relpath(CANDIDATES_JSON, ROOT)}, {os.path.relpath(CANDIDATES_MD, ROOT)}, "
        f"{os.path.relpath(STATE_PATH, ROOT)}")


if __name__ == "__main__":
    main()
