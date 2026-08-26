"""Pure parser tests for link auto-detect (no network)."""
from __future__ import annotations

from app.linkpreview import parse_meta

JSONLD = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "title":"Graduate Software Engineer",
 "hiringOrganization":{"@type":"Organization","name":"Stripe"}}
</script>
</head><body></body></html>
"""

JSONLD_GRAPH = """
<html><head>
<script type="application/ld+json">
{"@graph":[{"@type":"WebPage"},
 {"@type":["JobPosting"],"title":"Quantitative Trader","hiringOrganization":"Jane Street"}]}
</script>
</head></html>
"""

OG_ONLY = """
<html><head>
<meta property="og:title" content="Risk Analyst Intern">
<meta property="og:site_name" content="DBS Bank">
</head></html>
"""

TITLE_ONLY = "<html><head><title>Data Analyst Intern</title></head></html>"

EMPTY = "<html><head></head><body>hello</body></html>"


def test_jsonld_jobposting():
    r = parse_meta(JSONLD)
    assert r["ok"] is True
    assert r["title"] == "Graduate Software Engineer"
    assert r["company"] == "Stripe"
    assert r["sector"] == "tech"


def test_jsonld_graph_and_string_org():
    r = parse_meta(JSONLD_GRAPH)
    assert r["title"] == "Quantitative Trader"
    assert r["company"] == "Jane Street"
    assert r["sector"] == "finance"


def test_open_graph_fallback():
    r = parse_meta(OG_ONLY)
    assert r["ok"] is True
    assert r["title"] == "Risk Analyst Intern"
    assert r["company"] == "DBS Bank"
    assert r["sector"] == "finance"


def test_title_only_fallback():
    r = parse_meta(TITLE_ONLY)
    assert r["ok"] is True
    assert "Data Analyst" in r["title"]


def test_nothing_found_is_not_ok():
    r = parse_meta(EMPTY)
    assert r["ok"] is False
    assert r["title"] == ""
