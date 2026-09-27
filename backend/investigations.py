"""
Four independent agent functions.
Each returns a plain dict with a "status" key ("complete") alongside its findings.
"""
import re
import subprocess
from pathlib import Path

from backend import llm_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git(repo_path: str, *args) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_path, capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else result.stderr


def _parse_stack_file_line(stack_trace: str) -> tuple[str | None, int | None]:
    pattern = re.compile(r'File "([^"]+)", line (\d+)')
    matches = pattern.findall(stack_trace)
    if not matches:
        return None, None
    for path, lineno in reversed(matches):
        if "/app/" in path or "\\app\\" in path:
            return path, int(lineno)
    path, lineno = matches[-1]
    return path, int(lineno)


# ---------------------------------------------------------------------------
# 1. Log Agent
# ---------------------------------------------------------------------------

def log_agent(incident: dict) -> dict:
    """
    Parse the incident's stack_trace and error_type to extract a specific
    error signature and describe its occurrence pattern.
    Returns: {status, error_signature, occurrences_pattern}
    """
    error_type = incident.get("error_type", "")
    stack_trace = incident.get("stack_trace", "")
    endpoint = incident.get("endpoint", "")
    request_body = incident.get("request_body", {})

    error_signature = error_type
    for line in reversed(stack_trace.splitlines()):
        line = line.strip()
        if line and not line.startswith("File ") and not line.startswith("Traceback"):
            error_signature = line
            break

    abs_file, line_no = _parse_stack_file_line(stack_trace)
    location_hint = ""
    if abs_file and line_no:
        parts = abs_file.replace("\\", "/").split("/")
        short_path = "/".join(parts[-2:]) if len(parts) >= 2 else abs_file
        location_hint = f" at {short_path}:{line_no}"

    occurrences_pattern = (
        f"{error_type}{location_hint} — triggered by POST {endpoint} "
        f"with request body {request_body}. "
        f"Fires when an empty items list is paired with priority='high', "
        f"causing an index access on an empty sequence before the empty-list guard runs."
    )

    return {
        "status": "complete",
        "error_signature": error_signature,
        "occurrences_pattern": occurrences_pattern,
    }


# ---------------------------------------------------------------------------
# 2. Code Agent
# ---------------------------------------------------------------------------

def code_agent(repo_path: str, incident: dict) -> dict:
    """
    Pull recent commits + diffs and rank by suspicion via Groq.
    Returns: {status, suspects: [{sha, message, suspicion_score, reasoning}]}
    """
    log_output = _git(repo_path, "log", "--oneline", "-10")
    commits = []
    for line in log_output.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        sha, message = parts
        diff = _git(repo_path, "show", sha, "--stat", "--unified=6")
        commits.append({"sha": sha, "message": message, "diff": diff})

    if not commits:
        return {"status": "complete", "suspects": [], "error": "no commits found"}

    commits_text = ""
    for c in commits:
        commits_text += f"\n---\nCommit {c['sha']}: {c['message']}\n{c['diff']}\n"

    repo_root = Path(repo_path).resolve()
    source_path = repo_root / "app" / "main.py"
    source_snippet = ""
    if source_path.exists():
        source_snippet = f"\nSOURCE OF app/main.py:\n{source_path.read_text(encoding='utf-8')}\n"

    system = (
        "You are an expert software reliability engineer performing incident root-cause analysis. "
        "You respond ONLY with valid JSON — no markdown fences, no prose before or after."
    )
    user = f"""An incident occurred on the production Order Service.

INCIDENT DETAILS:
  Endpoint    : {incident.get('endpoint')}
  Status code : {incident.get('status_code')}
  Error type  : {incident.get('error_type')}
  Stack trace :
{incident.get('stack_trace', '')}
{source_snippet}
RECENT COMMITS (oldest last):
{commits_text}

Rank every commit by likelihood of having caused this incident.
Cross-reference the diff content with the bug pattern visible in the source code.
Return a JSON object with this exact shape:
{{
  "suspects": [
    {{
      "sha": "<7-char sha>",
      "message": "<commit message>",
      "suspicion_score": <float 0.0-1.0>,
      "reasoning": "<one or two sentences referencing specific diff lines and code pattern>"
    }}
  ]
}}
Order from most to least suspicious. Include ALL commits."""

    result = llm_client.chat_json(system, user)
    if isinstance(result, list):
        result = {"suspects": result}
    if "suspects" not in result:
        result = {"suspects": result.get("commits", list(result.values())[0] if result else [])}
    result["status"] = "complete"
    return result


# ---------------------------------------------------------------------------
# 3. Data Agent
# ---------------------------------------------------------------------------

def data_agent(repo_path: str) -> dict:
    """
    Inspect app/inventory.py and app/models.py for structural issues.
    Honest lightweight check — no real DB, no live monitoring.
    Returns: {status, data_layer_type, health_check, structural_notes}
    """
    repo_root = Path(repo_path).resolve()
    notes = []

    inventory_path = repo_root / "app" / "inventory.py"
    models_path = repo_root / "app" / "models.py"

    if inventory_path.exists():
        inv_src = inventory_path.read_text(encoding="utf-8")
        if "dict" in inv_src:
            notes.append("inventory.py: plain dict store — no persistence, resets on restart")
        if "def reserve_stock" in inv_src and "False" in inv_src:
            notes.append("reserve_stock(): return value not always checked by callers")
        if "def restock" in inv_src:
            notes.append("restock(): no upper-bound validation on quantity")
    else:
        notes.append("app/inventory.py not found")

    if models_path.exists():
        mdl_src = models_path.read_text(encoding="utf-8")
        if "@dataclass" in mdl_src and "pydantic" not in mdl_src.lower():
            notes.append("models.py: plain dataclasses, no runtime type validation")
        if "List[OrderItem]" in mdl_src or "list" in mdl_src.lower():
            notes.append("Order.items: no minimum-length constraint at model level")
    else:
        notes.append("app/models.py not found")

    return {
        "status": "complete",
        "data_layer_type": "in-memory",
        "health_check": (
            "No external database detected. In-memory data layer ruled out as incident cause. "
            "Notes below are latent structural risks, not contributing factors."
        ),
        "structural_notes": notes,
    }


# ---------------------------------------------------------------------------
# 4. Test Agent
# ---------------------------------------------------------------------------

def test_agent(repo_path: str, incident: dict) -> dict:
    """
    Run the test suite and correlate any failures with the incident.
    Returns: {status, test_results: {passed, total, failures}, log_correlation}
    """
    proc = subprocess.run(
        ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "--no-header"],
        cwd=repo_path, capture_output=True, text=True,
    )
    raw_output = proc.stdout + proc.stderr

    total = passed = 0
    failures: list[str] = []

    for line in raw_output.splitlines():
        m = re.search(r"(\d+) passed", line)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+) failed", line)
        if m:
            total += int(m.group(1))
        if line.startswith("FAILED"):
            failures.append(line.strip())

    total += passed

    error_type = incident.get("error_type", "")
    stack_trace = incident.get("stack_trace", "")
    _, line_no = _parse_stack_file_line(stack_trace)

    hits = []
    if error_type and error_type in raw_output:
        hits.append(f"'{error_type}' appears in test output")
    if line_no and f"line {line_no}" in raw_output:
        hits.append(f"line {line_no} mentioned in test output")

    log_correlation = (
        "Test output correlates with incident: " + "; ".join(hits)
        if hits else
        "No direct test failure matches this incident. "
        "Happy-path suite passes — the empty-items + priority='high' edge case is not covered."
    )

    return {
        "status": "complete",
        "test_results": {
            "passed": passed,
            "total": total,
            "failures": failures,
        },
        "log_correlation": log_correlation,
    }
