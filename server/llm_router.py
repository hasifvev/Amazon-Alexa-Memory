"""LLM-powered intent router using Amazon Bedrock.

Routes freeform user text to the correct MCP tool + arguments.
Architecture mirrors what real Alexa+ does: LLM decides intent → tool executes.

Fallback chain:  Nova Micro → Claude Haiku → regex (offline mode)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool registry — every tool the router can dispatch to
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "catch_me_up",
        "desc": "Greet the user and brief them on what's changed. Triggers: 'hi', 'hello', 'hey', 'good morning', 'catch me up', 'anything new', 'what's up', 'brief me', 'wake up'.",
        "args": {"full": "boolean, true if user wants full/detailed briefing"},
    },
    {
        "name": "set_profile",
        "desc": "Store personal info about the user: name, location, timezone, preferences. Triggers: 'my name is X', 'I live in Y', 'call me Z', 'I'm from Y', 'my timezone is Z'.",
        "args": {"key": "one of: name, location, timezone", "value": "the value to store"},
    },
    {
        "name": "what_time_is_it",
        "desc": "Tell the user the current time, date, or day. Triggers: 'what time', 'what day', 'what's today', 'current time', 'is it Friday'.",
        "args": {},
    },
    {
        "name": "add_to_list",
        "desc": "Add an item to a named list (shopping, packing, todo, etc). Triggers: 'add X to Y list', 'I need X', 'buy X', 'pick up X', 'grab some X'.",
        "args": {"item": "what to add", "list_name": "which list, default 'shopping'"},
    },
    {
        "name": "get_list",
        "desc": "Read all items on a named list. Triggers: 'what's on my list', 'shopping list', 'show my list', 'what do I need to buy'.",
        "args": {"list_name": "which list to read, default 'shopping'"},
    },
    {
        "name": "remove_from_list",
        "desc": "Remove/check off an item from a list. Triggers: 'remove X from list', 'I got the X', 'cross off X', 'done with X', 'bought X'.",
        "args": {"item": "what to remove", "list_name": "which list, default 'shopping'"},
    },
    {
        "name": "track",
        "desc": "Track a project or goal with a status. Triggers: 'track X as Y', 'X is now Y', 'update X to Y', 'started working on X'.",
        "args": {"project": "project name", "status": "status like building/planning/done/shipped", "note": "optional note"},
    },
    {
        "name": "my_projects",
        "desc": "List all tracked projects and their statuses. Triggers: 'what am I working on', 'my projects', 'active projects', 'show projects'.",
        "args": {},
    },
    {
        "name": "remember",
        "desc": "Store a fact permanently. Triggers: 'remember that X', 'note X', 'save X', 'don't forget X', 'keep in mind X'.",
        "args": {"fact": "the fact to remember"},
    },
    {
        "name": "remember_for",
        "desc": "Store a fact with an expiry. Triggers: 'remember X until Y', 'note X just for today', 'remember X for the next week'.",
        "args": {"fact": "the fact", "until": "when it expires"},
    },
    {
        "name": "recall",
        "desc": "Retrieve a stored fact. Triggers: 'what is X', 'do you remember X', 'tell me about X', any question about something stored.",
        "args": {"about": "what to look up", "when": "optional past date for time-travel recall"},
    },
    {
        "name": "correct",
        "desc": "Update/correct a previously stored fact. Triggers: 'change X to Y', 'correct X to Y', 'actually X is Y', 'fix X'.",
        "args": {"about": "what to correct", "new_fact": "the corrected value"},
    },
    {
        "name": "forget",
        "desc": "Withdraw/delete a stored fact. Triggers: 'forget X', 'never mind X', 'disregard X', 'scratch that'.",
        "args": {"about": "what to forget"},
    },
    {
        "name": "share",
        "desc": "Share a fact with another household member. Triggers: 'tell X that Y', 'let X know Y', 'share with X that Y', 'message X about Y'.",
        "args": {"fact": "what to share", "with_who": "person to share with"},
    },
    {
        "name": "shared_with_me",
        "desc": "Check what others have shared with you. Triggers: 'anything shared with me', 'messages for me', 'what did X share'.",
        "args": {},
    },
    {
        "name": "what_changed",
        "desc": "Show recent memory changes/updates. Triggers: 'what changed', 'what's different', 'recent changes', 'what happened since'.",
        "args": {"since": "time range, default '14 days ago'"},
    },
    {
        "name": "what_moved",
        "desc": "Show facts that have evolved/been corrected over time. Triggers: 'what has moved', 'biggest changes', 'what evolved'.",
        "args": {},
    },
    {
        "name": "wrong_about",
        "desc": "Show facts the user was wrong about (retracted/corrected). Triggers: 'what was I wrong about', 'my mistakes', 'what did I retract'.",
        "args": {},
    },
    {
        "name": "timeline",
        "desc": "Show the history of a specific fact over time. Triggers: 'history of X', 'timeline of X', 'how has X changed', 'what have I believed about X'.",
        "args": {"about": "the topic to show history for"},
    },
]


# ---------------------------------------------------------------------------
# Build the system prompt
# ---------------------------------------------------------------------------
def _build_system_prompt() -> str:
    tool_lines = []
    for t in TOOLS:
        args_str = ", ".join(f"{k}: {v}" for k, v in t["args"].items()) if t["args"] else "none"
        tool_lines.append(f"- **{t['name']}** ({args_str}): {t['desc']}")

    return f"""You are a routing engine for Alexa's memory assistant. Given the user's message, decide which single tool to call and extract the arguments.

Available tools:
{chr(10).join(tool_lines)}

Rules:
1. Return ONLY a valid JSON object with "tool" (string) and "args" (object). No markdown, no explanation.
2. For "args", include only the keys that are relevant. Omit optional args that aren't mentioned.
3. If the user says something like "I need milk" or "buy eggs", route to add_to_list with list_name "shopping".
4. If the user asks a question about something they've stored, route to recall.
5. If the user says hello/hey/hi/good morning or asks what's new, route to catch_me_up.
6. For "correct", set new_fact to include the corrected value as a full sentence.
7. Default list_name is "shopping" if not specified.

Example outputs:
{{"tool":"set_profile","args":{{"key":"name","value":"Hasif"}}}}
{{"tool":"add_to_list","args":{{"item":"milk","list_name":"shopping"}}}}
{{"tool":"catch_me_up","args":{{}}}}
{{"tool":"recall","args":{{"about":"wifi password"}}}}"""


# ---------------------------------------------------------------------------
# Bedrock invocation (Nova Micro -> Claude Haiku fallback)
# ---------------------------------------------------------------------------
_bedrock_rt = None


def _get_bedrock():
    global _bedrock_rt
    if _bedrock_rt is None:
        try:
            import boto3
            _bedrock_rt = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        except Exception as e:
            log.warning("Bedrock client init failed: %s", e)
            return None
    return _bedrock_rt


def _invoke_nova(client, user_text: str) -> dict | None:
    """Call Amazon Nova Micro for routing."""
    try:
        resp = client.invoke_model(
            modelId="amazon.nova-micro-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "messages": [
                    {"role": "user", "content": [{"text": _build_system_prompt() + "\n\nUser message: " + user_text}]},
                ],
                "inferenceConfig": {"maxTokens": 150, "temperature": 0},
            }),
        )
        raw = json.loads(resp["body"].read())
        text = raw.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
        return _parse_json(text)
    except Exception as e:
        log.warning("Nova Micro failed: %s", e)
        return None


def _invoke_haiku(client, user_text: str) -> dict | None:
    """Fallback to Claude Haiku on Bedrock."""
    try:
        resp = client.invoke_model(
            modelId="anthropic.claude-haiku-4-5-20251001-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "system": _build_system_prompt(),
                "messages": [{"role": "user", "content": user_text}],
                "max_tokens": 150,
                "temperature": 0,
            }),
        )
        raw = json.loads(resp["body"].read())
        text = raw.get("content", [{}])[0].get("text", "")
        return _parse_json(text)
    except Exception as e:
        log.warning("Claude Haiku failed: %s", e)
        return None


def _parse_json(text: str) -> dict | None:
    """Extract a JSON object from LLM output (may have markdown fences)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        obj = json.loads(text)
        if "tool" in obj:
            return obj
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]+\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def route_with_llm(user_text: str, who: str = "") -> dict | None:
    """Route user text to a tool using Bedrock LLM. Returns {"tool":..., "args":...} or None."""
    client = _get_bedrock()
    if client is None:
        return None

    # Try Nova Micro first (Amazon's model - best for hackathon optics)
    result = _invoke_nova(client, user_text)
    if result:
        if who and "who" not in result.get("args", {}):
            result["args"]["who"] = who
        log.info("LLM routed '%s' -> %s (Nova Micro)", user_text, result["tool"])
        return result

    # Fallback to Claude Haiku
    result = _invoke_haiku(client, user_text)
    if result:
        if who and "who" not in result.get("args", {}):
            result["args"]["who"] = who
        log.info("LLM routed '%s' -> %s (Claude Haiku)", user_text, result["tool"])
        return result

    log.warning("LLM routing failed for '%s', falling back to regex", user_text)
    return None
