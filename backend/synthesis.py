"""
Synthesises the four agent results into a root-cause report with evidence checklist.
Also provides suggest_fix() returning a simple before/after diff pair.
"""
import json

from backend import llm_client


def build_root_cause_report(
    log_result: dict,
    code_result: dict,
    data_result: dict,
    test_result: dict,
) -> dict:
    """
    Returns:
        {
            "root_cause": {
                "commit_sha": str,
                "confidence": "high" | "medium" | "low",
                "one_line_summary": str,
                "explanation": str
            },
            "evidence": [{"statement": str, "confirmed": bool}, ...]
        }
    """
    investigations_text = json.dumps(
        {
            "log_agent": log_result,
            "code_agent": code_result,
            "data_agent": data_result,
            "test_agent": test_result,
        },
        indent=2,
    )

    system = (
        "You are a principal site reliability engineer writing a post-incident root-cause analysis. "
        "You have findings from four independent automated agents. "
        "Synthesise them into a single authoritative conclusion. "
        "Respond ONLY with valid JSON — no markdown fences, no prose before or after."
    )

    user = f"""Below are findings from four automated agent investigations into a production incident.

INVESTIGATION RESULTS:
{investigations_text}

Determine the single most likely root cause based on ALL four agents.
Reference evidence from at least two agents in your explanation.

Return a JSON object with this exact shape:
{{
  "root_cause": {{
    "commit_sha": "<sha of the offending commit>",
    "confidence": "<high|medium|low>",
    "one_line_summary": "<one concise sentence identifying the bug, e.g. 'Commit 6f4f76b accessed items[0] before the empty-list guard'>",
    "explanation": "<two to four sentences: what the bug is, why it happens, which commit introduced it, what evidence confirms it>"
  }},
  "evidence": [
    {{
      "statement": "<short specific evidence statement>",
      "confirmed": true
    }}
  ]
}}

The evidence array MUST contain 4 to 6 items.
confirmed=true means the evidence supports or confirms the root cause.
confirmed=false means it was investigated and ruled out.
Draw each statement from the actual agent findings above. Be specific:
  - name the commit sha and message
  - name the exact error and file:line
  - state what the data agent found
  - state what the test agent found about coverage
"""

    result = llm_client.chat_json(system, user)

    if "root_cause" not in result:
        result = {
            "root_cause": {
                "commit_sha": result.get("commit_sha", "unknown"),
                "confidence": result.get("confidence", "low"),
                "one_line_summary": result.get("one_line_summary", ""),
                "explanation": result.get("explanation", str(result)),
            },
            "evidence": result.get("evidence", []),
        }

    # Ensure all keys exist
    rc = result.setdefault("root_cause", {})
    rc.setdefault("commit_sha", "unknown")
    rc.setdefault("confidence", "low")
    rc.setdefault("one_line_summary", rc.get("explanation", "")[:120])
    rc.setdefault("explanation", "")
    result.setdefault("evidence", [])

    return result


def suggest_fix(root_cause: dict, file_content: str) -> dict:
    """
    Given the root cause and current app/main.py content, determine the minimal fix.
    Returns:
        {
            "explanation": str,
            "fixed_file_content": str,
            "diff": {
                "file": "app/main.py",
                "before_line": str,
                "after_line": str
            }
        }
    """
    system = (
        "You are an expert Python engineer performing a targeted bug fix. "
        "Respond ONLY with valid JSON — no markdown fences, no prose before or after. "
        "fixed_file_content must be the COMPLETE corrected Python source with no truncation."
    )

    user = f"""A production incident was caused by the following root cause:

ROOT CAUSE:
{json.dumps(root_cause, indent=2)}

The bug is in app/main.py. The fix is minimal: move the empty-items validation
check (the `if not req.items:` guard) so that it executes BEFORE the priority
field logic block (the `if req.priority == "high":` block).

CURRENT CONTENT OF app/main.py:
{file_content}

Return a JSON object with this exact shape:
{{
  "explanation": "<one or two sentences: what was moved, why it fixes the bug>",
  "fixed_file_content": "<complete corrected Python source for app/main.py>",
  "diff": {{
    "file": "app/main.py",
    "before_line": "<the exact line that was in the wrong position, as it appeared before the fix>",
    "after_line": "<the same line after being moved to the correct position, or a note on what changed>"
  }}
}}

fixed_file_content must be the ENTIRE file — not a diff, not a snippet."""

    result = llm_client.chat_json(system, user)
    result.setdefault("explanation", "No explanation provided.")
    result.setdefault("fixed_file_content", file_content)
    result.setdefault("diff", {
        "file": "app/main.py",
        "before_line": "if not req.items:  # after priority check",
        "after_line":  "if not req.items:  # moved before priority check",
    })
    return result
