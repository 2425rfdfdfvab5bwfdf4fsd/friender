"""Coding Agent tools — AI-powered code generation, explanation, refactoring, and testing."""
from __future__ import annotations
from pathlib import Path

_llm_client = None

_CODE_SYSTEM = """You are PACCA's Coding Agent — a senior software engineer with expertise across all languages.

Rules:
- When generating code: output ONLY raw code with no markdown fences, no preamble, no explanation.
- When explaining/reviewing code: use clear markdown with headers and bullet points.
- When refactoring: output ONLY the refactored code, no explanations unless asked.
- When writing tests: output ONLY the test file code, no fences.
- Be precise, idiomatic, and production-quality."""

_EXPLAIN_SYSTEM = """You are PACCA's Code Explainer. Given source code, produce a clear markdown explanation covering:
1. **Purpose** — what this code does in one sentence
2. **Architecture** — how it's structured (classes, functions, patterns)
3. **Key logic** — the most important algorithms or decisions
4. **Dependencies** — external libraries or modules used
5. **Potential issues** — any bugs, code smells, or security concerns
6. **Suggested improvements** — specific, actionable improvements

Be concise but thorough. Use code blocks for examples."""

_QUALITY_SYSTEM = """You are PACCA's Code Quality Analyzer. Review the given code and produce a structured report:

## Quality Score: X/10

### ✅ Strengths
(bullet list)

### ⚠ Issues Found
For each issue: severity (CRITICAL/HIGH/MEDIUM/LOW), description, line reference if possible, fix suggestion.

### 🔒 Security
Any security concerns (injection, hardcoded secrets, unsafe operations).

### 🚀 Performance
Any performance bottlenecks or inefficiencies.

### ✅ Recommendation
One paragraph summary with the top 3 action items."""


def set_llm_client(client) -> None:
    global _llm_client
    _llm_client = client


import re as _re
_FENCE_RE = _re.compile(r'^```[^\n]*\n(.*?)(?:\n```\s*)?$', _re.DOTALL)

def _strip_code_fences(text: str) -> str:
    """Remove outer markdown code fences safely, preserving interior backticks."""
    text = text.strip()
    m = _FENCE_RE.match(text)
    if m:
        return m.group(1).strip()
    return text


def _require_llm() -> object:
    if _llm_client is None or not _llm_client.is_available():
        hint = _llm_client.key_error() if _llm_client else "No LLM client configured."
        raise RuntimeError(
            f"Code tools require a working LLM API key. {hint or 'Add one in Replit Secrets (🔒).'}"
        )
    return _llm_client


def _read_source(file_path: str) -> tuple[str, str]:
    """Read a source file. Returns (content, language)."""
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    content = p.read_text(encoding="utf-8", errors="replace")
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx", ".go": "go", ".rs": "rust",
        ".java": "java", ".cpp": "c++", ".c": "c", ".cs": "csharp",
        ".rb": "ruby", ".php": "php", ".swift": "swift", ".kt": "kotlin",
        ".sh": "bash", ".sql": "sql", ".html": "html", ".css": "css",
    }
    lang = ext_map.get(p.suffix.lower(), "code")
    return content, lang


async def generate_code(description: str, language: str = "python",
                         output_path: str | None = None,
                         dry_run: bool = False) -> dict:
    """Generate production-quality code from a natural language description."""
    if dry_run:
        return {"dry_run": True, "description": description, "language": language,
                "would_save": output_path}

    client = _require_llm()
    prompt = (
        f"Write {language} code that does the following:\n\n{description}\n\n"
        "Output ONLY the raw code. No markdown fences, no explanation, no preamble."
    )
    code = await client._call(_CODE_SYSTEM, prompt, max_tokens=4096)
    code = _strip_code_fences(code)

    result: dict = {"code": code, "language": language, "description": description[:100]}

    if output_path:
        p = Path(output_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code, encoding="utf-8")
        result["saved"] = str(p)

    return result


async def explain_code(file_path: str, dry_run: bool = False) -> dict:
    """Read a source file and produce a detailed AI explanation."""
    if dry_run:
        return {"dry_run": True, "would_explain": file_path}

    client = _require_llm()
    content, lang = _read_source(file_path)
    prompt = f"Language: {lang}\n\nSource code:\n```{lang}\n{content[:12000]}\n```"
    explanation = await client._call(_EXPLAIN_SYSTEM, prompt, max_tokens=3000)
    return {
        "file": file_path,
        "language": lang,
        "lines": len(content.splitlines()),
        "explanation": explanation,
    }


async def refactor_code(file_path: str, instructions: str,
                         save_result: bool = True,
                         dry_run: bool = False) -> dict:
    """Refactor source code according to natural language instructions."""
    if dry_run:
        return {"dry_run": True, "would_refactor": file_path, "instructions": instructions}

    client = _require_llm()
    content, lang = _read_source(file_path)
    prompt = (
        f"Refactor the following {lang} code according to these instructions:\n"
        f"Instructions: {instructions}\n\n"
        f"Source:\n```{lang}\n{content[:10000]}\n```\n\n"
        "Output ONLY the refactored code. No markdown fences, no explanation."
    )
    refactored = await client._call(_CODE_SYSTEM, prompt, max_tokens=4096)
    refactored = _strip_code_fences(refactored)

    result: dict = {
        "file": file_path,
        "language": lang,
        "instructions": instructions,
        "refactored_code": refactored,
        "original_lines": len(content.splitlines()),
        "new_lines": len(refactored.splitlines()),
    }

    if save_result:
        p = Path(file_path).expanduser()
        p.write_text(refactored, encoding="utf-8")
        result["saved"] = str(p)

    return result


async def write_tests(file_path: str, test_framework: str = "pytest",
                       output_path: str | None = None,
                       dry_run: bool = False) -> dict:
    """Generate a comprehensive test suite for a source file."""
    if dry_run:
        return {"dry_run": True, "would_test": file_path, "framework": test_framework}

    client = _require_llm()
    content, lang = _read_source(file_path)
    p = Path(file_path).expanduser()

    if output_path is None:
        output_path = str(p.parent / f"test_{p.stem}{p.suffix}")

    system = (
        f"You are a test engineer. Write a comprehensive {test_framework} test suite "
        f"for the given {lang} code. Cover: happy paths, edge cases, error conditions. "
        "Output ONLY the raw test file code. No fences, no explanation."
    )
    prompt = (
        f"Write {test_framework} tests for this {lang} code:\n\n"
        f"```{lang}\n{content[:10000]}\n```\n\n"
        "Output ONLY the test file. No markdown, no explanation."
    )
    tests = await client._call(system, prompt, max_tokens=4096)
    tests = _strip_code_fences(tests)

    out_p = Path(output_path).expanduser()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(tests, encoding="utf-8")

    return {
        "source_file": file_path,
        "test_file": str(out_p),
        "framework": test_framework,
        "test_lines": len(tests.splitlines()),
    }


async def analyze_code_quality(file_path: str, dry_run: bool = False) -> dict:
    """Perform a comprehensive AI code quality review."""
    if dry_run:
        return {"dry_run": True, "would_analyze": file_path}

    client = _require_llm()
    content, lang = _read_source(file_path)
    prompt = (
        f"Language: {lang}\nFile: {file_path}\n"
        f"Lines: {len(content.splitlines())}\n\n"
        f"Code:\n```{lang}\n{content[:10000]}\n```"
    )
    review = await client._call(_QUALITY_SYSTEM, prompt, max_tokens=3000)
    return {
        "file": file_path,
        "language": lang,
        "lines": len(content.splitlines()),
        "review": review,
    }
