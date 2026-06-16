"""Research Agent — multi-source web research with AI synthesis and report generation."""
from __future__ import annotations
import time
import urllib.parse
from pathlib import Path

_llm_client = None
_memory_manager = None


def set_memory_manager(manager) -> None:
    global _memory_manager
    _memory_manager = manager

_SYNTHESIS_SYSTEM = """You are Arix's Research Agent. You synthesize web research into clear, structured reports.

Your reports follow this format:

# {topic}
*Research Report — {date}*

## Executive Summary
(2-3 sentence TL;DR)

## Key Findings
(numbered list of the most important facts with source citations)

## Detailed Analysis
(section per major sub-topic found in the research)

## Comparison / Data Table (if applicable)
(markdown table comparing key options/players/stats)

## Sources
(numbered list of URLs researched)

## Conclusion & Recommendations
(concrete, actionable takeaways)

Be factual. Cite sources inline with [1], [2] etc. Do not invent facts not present in the source material."""

_QUERY_SYSTEM = """You are a research assistant. Given a research topic, generate 3-5 targeted search queries 
that together will give comprehensive coverage of the topic. 
Output ONLY a JSON array of query strings. No explanation. Example:
["query one", "query two", "query three"]"""


def set_llm_client(client) -> None:
    global _llm_client
    _llm_client = client


def _require_llm():
    if _llm_client is None or not _llm_client.is_available():
        hint = _llm_client.key_error() if _llm_client else "No LLM client configured."
        raise RuntimeError(
            f"Research tools require a working LLM API key. {hint or 'Add one in Replit Secrets (🔒).'}"
        )
    return _llm_client


async def _generate_queries(topic: str) -> list[str]:
    """Use LLM to generate targeted search queries for the topic."""
    client = _require_llm()
    try:
        raw = await client._call(_QUERY_SYSTEM,
                                  f"Research topic: {topic}", max_tokens=256)
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:])
            if "```" in raw:
                raw = raw[:raw.rfind("```")].strip()
        import json
        queries = json.loads(raw)
        if isinstance(queries, list):
            return [str(q) for q in queries[:5]]
    except Exception:
        pass
    return [topic, f"{topic} overview", f"{topic} best practices"]


async def _search_and_extract(query: str) -> dict:
    """Search for a query and extract text from the top result."""
    from arix.tools.browser_tools import get_browser_controller
    controller = get_browser_controller()
    if not controller._page:
        await controller.start()

    search_url = "https://duckduckgo.com/?q=" + urllib.parse.quote(query)
    try:
        await controller._page.goto(search_url, timeout=20000,
                                     wait_until="domcontentloaded")
        # Extract the first few result links
        links = await controller._page.evaluate("""() => {
            const anchors = document.querySelectorAll('a[href^="http"]');
            const urls = [];
            anchors.forEach(a => {
                const href = a.href;
                if (!href.includes('duckduckgo') && !href.includes('duck.co') &&
                    !href.includes('javascript:') && urls.length < 3) {
                    urls.push(href);
                }
            });
            return urls;
        }""")

        # Extract text from the search results page itself
        text = await controller._page.evaluate("""() => {
            const el = document.body;
            return el ? el.innerText.substring(0, 4000) : '';
        }""")

        return {
            "query": query,
            "search_url": search_url,
            "result_links": links[:3],
            "excerpt": text[:3000],
        }
    except Exception as e:
        return {"query": query, "error": str(e), "excerpt": ""}


async def research_topic(topic: str, depth: int = 3,
                          output_path: str | None = None,
                          dry_run: bool = False) -> dict:
    """Perform deep multi-source web research on a topic and synthesize a structured report.
    
    Args:
        topic: The research topic or question
        depth: Number of search queries to run (1-5)
        output_path: Optional path to save the report as a .md file
    """
    if dry_run:
        return {"dry_run": True, "topic": topic, "depth": depth, "output": output_path}

    client = _require_llm()
    depth = max(1, min(5, depth))

    # Step 1: Generate targeted queries
    queries = await _generate_queries(topic)
    queries = queries[:depth]

    # Step 2: Search all queries
    research_data = []
    for q in queries:
        result = await _search_and_extract(q)
        research_data.append(result)

    # Step 3: Compile all excerpts into a synthesis prompt
    compiled = []
    sources = []
    for i, r in enumerate(research_data, 1):
        if r.get("excerpt"):
            compiled.append(f"[Source {i}] Query: {r['query']}\n{r['excerpt'][:2000]}")
        if r.get("search_url"):
            sources.append(r["search_url"])
        sources.extend(r.get("result_links", []))

    all_text = "\n\n---\n\n".join(compiled)
    date_str = time.strftime("%B %d, %Y")
    sources_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sources[:10]))

    _MAX_RESEARCH_CHARS = 12000
    truncation_note = ""
    if len(all_text) > _MAX_RESEARCH_CHARS:
        truncation_note = f"\n[NOTE: Research data truncated from {len(all_text):,} to {_MAX_RESEARCH_CHARS:,} chars for synthesis]"
    synthesis_prompt = (
        f"Research Topic: {topic}\n"
        f"Date: {date_str}\n"
        f"Sources consulted: {len(research_data)} search queries\n\n"
        f"Raw research data:\n{all_text[:_MAX_RESEARCH_CHARS]}{truncation_note}\n\n"
        f"Source URLs:\n{sources_str}\n\n"
        f"Synthesize this into a comprehensive research report."
    )

    # Step 4: Synthesize
    report = await client._call(_SYNTHESIS_SYSTEM, synthesis_prompt, max_tokens=4096)

    result: dict = {
        "topic": topic,
        "queries_run": queries,
        "sources_checked": len(sources),
        "report": report,
        "generated_at": date_str,
    }

    saved_path = ""
    # Step 5: Optionally save to file
    if output_path:
        p = Path(output_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(report, encoding="utf-8")
        result["saved"] = str(p)
        saved_path = str(p)

    # Step 6: Persist to memory reports store
    if _memory_manager is not None:
        try:
            report_id = _memory_manager.store_report(
                topic=topic,
                content=report,
                queries_run=queries,
                sources_count=len(sources),
                saved_path=saved_path,
            )
            result["report_id"] = report_id
        except Exception as _e:
            result["report_store_warning"] = f"Report generated but not saved to memory: {_e}"

    return result


async def summarize_url(url: str, dry_run: bool = False) -> dict:
    """Navigate to a URL and produce a concise AI summary of its content."""
    if dry_run:
        return {"dry_run": True, "would_summarize": url}

    from arix.tools.browser_tools import get_browser_controller, _check_url_safety
    safe, reason = _check_url_safety(url)
    if not safe:
        return {"error": reason, "blocked": True}

    client = _require_llm()
    controller = get_browser_controller()
    if not controller._page:
        await controller.start()

    try:
        response = await controller._page.goto(url, timeout=25000,
                                                wait_until="domcontentloaded")
        title = await controller._page.title()
        text = await controller._page.evaluate("""() => {
            ['script','style','nav','footer','header','aside'].forEach(t =>
                document.querySelectorAll(t).forEach(e => e.remove()));
            return document.body ? document.body.innerText : '';
        }""")

        system = (
            "You are a content summarizer. Given the text from a web page, produce:\n"
            "1. **Title**: The page title\n"
            "2. **TL;DR**: One sentence summary\n"
            "3. **Key Points**: 5-7 bullet points of the most important information\n"
            "4. **Verdict**: Is this source credible and useful? Why?\n\n"
            "Be concise and factual."
        )
        prompt = f"URL: {url}\nTitle: {title}\n\nPage content:\n{text[:8000]}"
        summary = await client._call(system, prompt, max_tokens=1500)

        return {
            "url": url,
            "title": title,
            "status": response.status if response else None,
            "summary": summary,
        }
    except Exception as e:
        return {"error": str(e), "url": url}
