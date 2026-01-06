from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import arxiv
import feedparser
import re


_ARXIV_CATEGORY_RE = re.compile(r"^[a-zA-Z-]+\.[a-zA-Z0-9-]+$")
_ARXIV_VERSION_SUFFIX_RE = re.compile(r"v\d+$")


def _normalize_arxiv_query_for_api(arxiv_query: str) -> str:
    """
    Normalize config `arxiv.query` into an arXiv API `search_query`.

    Supports:
      - RSS-style category lists like: "cs.AI+cs.LG+cs.CL"
      - Raw arXiv API queries like: "cat:cs.AI OR cat:cs.LG"
        (also accepts URL-encoded '+' and turns them into spaces)
    """
    query = (arxiv_query or "").strip()
    if not query:
        raise ValueError("Empty arXiv query")

    # If the query is a pure category list (RSS-style), convert to API syntax.
    if ":" not in query:
        parts = [p for p in re.split(r"[+,\s]+", query) if p]
        if parts and all(_ARXIV_CATEGORY_RE.match(p) for p in parts):
            return " OR ".join([f"cat:{p}" for p in parts])

    # Otherwise treat it as an arXiv API query; decode '+' (common in config examples).
    return query.replace("+", " ")


def _extract_categories_from_query(arxiv_query: str) -> Optional[List[str]]:
    """
    If `arxiv_query` looks like an RSS-style category list (e.g. "cs.AI+cs.LG"),
    return the parsed categories; otherwise return None.
    """
    query = (arxiv_query or "").strip()
    if not query or ":" in query:
        return None
    parts = [p for p in re.split(r"[+,\s]+", query) if p]
    if parts and all(_ARXIV_CATEGORY_RE.match(p) for p in parts):
        return parts
    return None


def _base_arxiv_id(result: arxiv.Result) -> str:
    """
    Return arXiv ID without version suffix (e.g. '2401.01234' from '2401.01234v2').
    """
    try:
        short_id = result.get_short_id()
    except Exception:
        short_id = (result.entry_id or "").rstrip("/").split("/")[-1]
    return _ARXIV_VERSION_SUFFIX_RE.sub("", short_id)


def _normalize_abstract(text: str) -> str:
    return " ".join((text or "").split())


def _result_to_dict(result: arxiv.Result) -> Dict:
    return {
        "id": _base_arxiv_id(result),
        "title": result.title,
        "abstract": _normalize_abstract(result.summary),
        "authors": [a.name for a in result.authors],
        "url": result.entry_id.replace("http://", "https://"),
        "link": result.entry_id.replace("http://", "https://"),
        "published": result.published.date().isoformat() if result.published else "",
    }


def _extract_new_ids(arxiv_query: str, only_new: bool = True, days_back: Optional[int] = 1) -> List[str]:
    feed = feedparser.parse(f"https://rss.arxiv.org/atom/{arxiv_query}")
    if "Feed error for query" in feed.feed.get("title", ""):
        raise ValueError(f"Invalid arXiv query: {arxiv_query}")

    cutoff = None
    if days_back is not None and days_back >= 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    ids: List[str] = []
    for entry in feed.entries:
        announce_type = entry.get("arxiv_announce_type")
        if only_new and announce_type not in ("new", None):
            continue  # if field missing, treat as new; else require "new"
        if cutoff:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                published_dt = datetime(*published[:6], tzinfo=timezone.utc)
                if published_dt < cutoff:
                    continue
        ids.append(entry.id.removeprefix("oai:arXiv.org:"))
    return ids


def fetch_daily_arxiv(
    arxiv_query: str,
    max_results: int = 50,
    client: Optional[arxiv.Client] = None,
    only_new: bool = True,
    days_back: Optional[int] = 1,
    source: str = "rss",
) -> List[Dict]:
    """
    Fetch arXiv papers for a given query string.

    - source="rss": uses arXiv RSS/Atom feed to discover "new" IDs, then resolves metadata via API.
      (may have a few hours delay depending on the feed)
    - source="api": queries the official arXiv API directly (export.arxiv.org/api/query) via the `arxiv` library.

    Returns a list of dicts with title, abstract, authors, url, published.
    """
    client = client or arxiv.Client(num_retries=3, delay_seconds=3)
    results: List[Dict] = []

    if source == "rss":
        ids = _extract_new_ids(arxiv_query, only_new=only_new, days_back=days_back)
        if not ids:
            return []
        if max_results > 0:
            ids = ids[:max_results]

        for i in range(0, len(ids), 20):
            search = arxiv.Search(id_list=ids[i : i + 20])
            for res in client.results(search):
                results.append(_result_to_dict(res))
        return results

    if source == "api":
        cutoff = None
        if only_new and days_back is not None and days_back >= 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        categories = _extract_categories_from_query(arxiv_query)
        if categories:
            dedup: Dict[str, Dict] = {}
            for category in categories:
                search = arxiv.Search(
                    query=f"cat:{category}",
                    max_results=max_results,
                    sort_by=arxiv.SortCriterion.SubmittedDate,
                    sort_order=arxiv.SortOrder.Descending,
                )
                for res in client.results(search):
                    if cutoff and res.published and res.published < cutoff:
                        break
                    paper = _result_to_dict(res)
                    dedup.setdefault(paper["id"], paper)

            merged = list(dedup.values())
            merged.sort(key=lambda p: p.get("published", ""), reverse=True)
            return merged[:max_results] if max_results > 0 else merged

        api_query = _normalize_arxiv_query_for_api(arxiv_query)
        search = arxiv.Search(
            query=api_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        for res in client.results(search):
            if cutoff and res.published and res.published < cutoff:
                break
            results.append(_result_to_dict(res))
        return results

    raise ValueError(f"Unknown arXiv source: {source!r} (expected 'rss' or 'api')")
