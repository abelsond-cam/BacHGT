"""LLM backend for the engine — a thin interface plus an Anthropic implementation.

The grading/finding stages depend only on the :class:`LLMClient` protocol, so the concrete
backend (Anthropic API today; an Agent-SDK / Pro-account backend later) can be swapped without
touching the rubric logic. The one method, :meth:`LLMClient.complete_structured`, returns
**validated structured JSON**: the Anthropic implementation uses Messages-API *forced tool use*
(the tool's ``input_schema`` is our JSON schema and ``tool_choice`` pins that tool), so the model
must return an object matching the schema — no free-text parsing.

Every response is cached on disk, keyed by a hash of (model, system, user, schema, decoding
params). This makes reruns deterministic and offline, and keeps cost down while iterating on the
rubric. ``temperature`` defaults to 0 for the same reason.

API-key resolution mirrors the repo's off-OneDrive secret convention (see ``engine/gsheet.py``):
``ANTHROPIC_API_KEY`` env var first, else the file ``~/.config/bac_metadata/anthropic_api_key``
(override its location with ``BAC_ANTHROPIC_KEY_FILE``). The key never lives in the repo.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

#: Default config dir, shared with the Google OAuth secrets (see ``engine/gsheet.py``).
CONFIG_DIR = Path(os.environ.get("BAC_GOOGLE_CONFIG_DIR", Path.home() / ".config" / "bac_metadata"))

#: Default + escalation models. Sonnet is the workhorse; escalate to Opus where agreement needs it.
DEFAULT_MODEL = "claude-sonnet-4-6"
ESCALATION_MODEL = "claude-opus-4-8"

#: Generous output ceiling for a single structured grade (the schema is small; this is headroom).
DEFAULT_MAX_TOKENS = 4096


def resolve_api_key() -> str:
    """Resolve the Anthropic API key: env var, else the off-OneDrive key file.

    Resolution order:
      1. ``ANTHROPIC_API_KEY`` environment variable.
      2. The file at ``BAC_ANTHROPIC_KEY_FILE`` if set, else
         ``~/.config/bac_metadata/anthropic_api_key`` (chmod 600, outside the repo).

    Returns
    -------
    str
        The API key, stripped of surrounding whitespace.

    Raises
    ------
    FileNotFoundError
        If neither the env var nor the key file provides a key.
    """
    env = os.environ.get("ANTHROPIC_API_KEY")
    if env and env.strip():
        return env.strip()
    key_file = Path(os.environ.get("BAC_ANTHROPIC_KEY_FILE", CONFIG_DIR / "anthropic_api_key"))
    if key_file.exists():
        text = key_file.read_text().strip()
        if text:
            return text
    raise FileNotFoundError(
        f"No Anthropic API key: set ANTHROPIC_API_KEY or write the key to {key_file} "
        "(chmod 600, off OneDrive)."
    )


@runtime_checkable
class LLMClient(Protocol):
    """Minimal structured-output interface the grading/finding stages depend on."""

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict,
        schema_name: str,
        schema_description: str = "",
        model: str | None = None,
    ) -> dict:
        """Return a dict validated against ``json_schema`` for the given prompt."""
        ...


def _cache_key(payload: dict) -> str:
    """Stable SHA-256 over a canonicalised request payload."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def request_cache_key(
    *,
    model: str,
    system: str,
    user: str,
    json_schema: dict,
    schema_name: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.0,
) -> str:
    """Backend-independent cache key for one logical grading request.

    Both backends derive the key from the *logical* request (model + prompts + schema), not from
    backend-specific rendering, so a result graded once (e.g. on the API) is reused verbatim by the
    other backend (e.g. the subscription). The payload shape is fixed for stable hashing.
    """
    return _cache_key(
        {
            "model": model,
            "system": system,
            "user": user,
            "schema": json_schema,
            "tool": schema_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    )


# --------------------------------------------------------------------------------------------- #
# Lightweight JSON-Schema validation (for backends without server-side schema enforcement).
# --------------------------------------------------------------------------------------------- #
_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _type_ok(instance: object, types: list[str]) -> bool:
    """Whether ``instance`` matches any JSON-Schema type name in ``types`` (``null`` → None)."""
    for t in types:
        if t == "null" and instance is None:
            return True
        py = _TYPE_MAP.get(t)
        if py is None:
            continue
        # bool is a subclass of int — only accept it for the boolean type.
        if py is int and isinstance(instance, bool):
            continue
        if isinstance(instance, py):
            return True
    return False


def schema_errors(instance: object, schema: dict, path: str = "") -> list[str]:
    """Return a list of human-readable validation errors (empty == valid).

    Supports the subset our grade schema uses: ``type`` (str or list), ``enum``,
    ``properties`` + ``required`` for objects. Unknown keywords are ignored.
    """
    where = path or "root"
    if "enum" in schema:
        return [] if instance in schema["enum"] else [f"{where}: {instance!r} not in {schema['enum']}"]
    t = schema.get("type")
    types = t if isinstance(t, list) else ([t] if t else [])
    if types and not _type_ok(instance, types):
        return [f"{where}: expected type {types}, got {type(instance).__name__}"]
    errs: list[str] = []
    if "object" in types and isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errs.append(f"{where}.{req}: missing required key")
        for key, sub in schema.get("properties", {}).items():
            if key in instance:
                errs.extend(schema_errors(instance[key], sub, f"{where}.{key}"))
    return errs


class AnthropicClient:
    """:class:`LLMClient` backed by the Anthropic Messages API with a disk cache.

    Parameters
    ----------
    model
        Default model id used when a call does not override it. Defaults to
        :data:`DEFAULT_MODEL` (Sonnet).
    cache_dir
        Directory for the response cache. If ``None``, responses are not cached (live every call).
    api_key
        Explicit key; if ``None`` it is resolved via :func:`resolve_api_key` on first use.
    max_tokens
        Output-token ceiling per call.
    temperature
        Decoding temperature; 0 for deterministic structured output.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        cache_dir: str | Path | None = None,
        api_key: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._api_key = api_key
        self._client = None  # lazily constructed so importing/structural use needs no key

    def _ensure_client(self):
        """Construct the Anthropic SDK client on first use (resolving the key lazily)."""
        if self._client is None:
            import anthropic

            if self._api_key is None:
                self._api_key = resolve_api_key()
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict,
        schema_name: str,
        schema_description: str = "",
        model: str | None = None,
    ) -> dict:
        """Return a dict matching ``json_schema`` via forced tool use (cached on disk).

        Parameters
        ----------
        system
            System prompt (the rubric framing).
        user
            User prompt (the per-accession evidence).
        json_schema
            JSON Schema the response object must satisfy (used as the tool's ``input_schema``).
        schema_name
            Tool name (must match ``^[a-zA-Z0-9_-]{1,64}$``); also the forced ``tool_choice``.
        schema_description
            Optional tool description shown to the model.
        model
            Per-call model override (e.g. escalate to :data:`ESCALATION_MODEL`).

        Returns
        -------
        dict
            The validated tool-input object the model produced.
        """
        use_model = model or self.model
        cache_path: Path | None = None
        if self.cache_dir is not None:
            key = request_cache_key(
                model=use_model,
                system=system,
                user=user,
                json_schema=json_schema,
                schema_name=schema_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            cache_path = self.cache_dir / f"{key}.json"
            if cache_path.exists():
                return json.loads(cache_path.read_text())

        client = self._ensure_client()
        resp = client.messages.create(
            model=use_model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[
                {
                    "name": schema_name,
                    "description": schema_description or f"Return a structured {schema_name}.",
                    "input_schema": json_schema,
                }
            ],
            tool_choice={"type": "tool", "name": schema_name},
        )
        result: dict | None = None
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                result = dict(block.input)
                break
        if result is None:
            raise RuntimeError(f"Model returned no tool_use block for tool '{schema_name}'.")

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result


class UsageLimitError(RuntimeError):
    """Raised when the Claude subscription usage window (5-hour / weekly) is exhausted.

    Callers should stop cleanly and resume later — the disk cache makes resume nearly free.
    """


#: Signatures of an exhausted usage window in the CLI output (case-insensitive).
_USAGE_LIMIT_RE = re.compile(
    r"usage limit|rate limit|limit reached|too many requests|\b429\b|reset at|upgrade to (?:pro|max)",
    re.IGNORECASE,
)
_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a single JSON object that conforms exactly to the JSON Schema below. "
    "No prose, no explanation, no markdown code fences — output just the JSON object.\n\n"
    "JSON Schema:\n"
)


def _extract_json_object(text: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences / surrounding prose."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s.strip())
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start : end + 1])
        raise


class ClaudeCliClient:
    """:class:`LLMClient` backed by the ``claude -p`` CLI on a Claude subscription (no API spend).

    Drives the installed ``claude`` CLI in headless single-turn mode using the machine's ambient
    subscription auth (keychain after ``claude`` login, or ``CLAUDE_CODE_OAUTH_TOKEN``). The CLI
    has no forced-tool-use, so the JSON Schema is embedded in the prompt; the reply is parsed and
    validated against the schema with one retry. Determinism comes from the shared disk cache.

    Parameters
    ----------
    model
        Default model id / alias (``claude-sonnet-4-6`` or ``sonnet`` / ``opus``).
    cache_dir
        Disk cache directory (shared, backend-independent key). ``None`` disables caching.
    timeout
        Per-call subprocess timeout in seconds.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        cache_dir: str | Path | None = None,
        timeout: int = 600,
    ) -> None:
        self.model = model
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.timeout = timeout
        self._bin: str | None = None
        self._workdir: str | None = None

    def _ensure_env(self) -> tuple[str, str]:
        """Resolve the ``claude`` binary + a neutral working dir (no repo CLAUDE.md leakage)."""
        if self._bin is None:
            found = shutil.which("claude")
            if found is None:
                raise FileNotFoundError("`claude` CLI not found on PATH; install it or use --backend api.")
            self._bin = found
        if self._workdir is None:
            self._workdir = tempfile.mkdtemp(prefix="bac_grade_")
        return self._bin, self._workdir

    def _run_cli(self, *, system: str, user: str, model: str) -> str:
        """Invoke ``claude -p`` once and return the assistant's result text (raises on limit/error)."""
        claude_bin, workdir = self._ensure_env()
        cmd = [
            claude_bin, "-p",
            "--system-prompt", system,
            "--model", model,
            "--output-format", "json",
            "--allowed-tools", "",
            "--no-session-persistence",
        ]
        # Fixed argv (no shell); inputs are our own prompts.
        try:
            proc = subprocess.run(cmd, input=user, capture_output=True, text=True, cwd=workdir, timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            # Surface as a normal error so the batch runner can skip this accession and continue,
            # rather than crashing the whole run on one slow paper.
            raise RuntimeError(f"claude -p timed out after {self.timeout}s") from exc
        combined = f"{proc.stdout}\n{proc.stderr}"
        if proc.returncode != 0:
            if _USAGE_LIMIT_RE.search(combined):
                raise UsageLimitError(f"Claude usage limit reached: {proc.stderr.strip()[:200]}")
            raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}")
        try:
            env = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"claude -p returned non-JSON envelope: {proc.stdout[:200]!r}") from exc
        result_text = str(env.get("result", ""))
        if env.get("is_error"):
            detail = f"{result_text} {env.get('subtype', '')}"
            if _USAGE_LIMIT_RE.search(detail):
                raise UsageLimitError(f"Claude usage limit reached: {detail.strip()[:200]}")
            raise RuntimeError(f"claude -p returned is_error: {detail.strip()[:300]}")
        if _USAGE_LIMIT_RE.search(result_text):
            raise UsageLimitError(f"Claude usage limit reached: {result_text.strip()[:200]}")
        return result_text

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict,
        schema_name: str,
        schema_description: str = "",
        model: str | None = None,
    ) -> dict:
        """Return a dict matching ``json_schema`` via ``claude -p`` (cached; one validation retry)."""
        use_model = model or self.model
        cache_path: Path | None = None
        if self.cache_dir is not None:
            key = request_cache_key(
                model=use_model, system=system, user=user, json_schema=json_schema, schema_name=schema_name
            )
            cache_path = self.cache_dir / f"{key}.json"
            if cache_path.exists():
                return json.loads(cache_path.read_text())

        schema_blob = json.dumps(json_schema, ensure_ascii=False)
        user_full = f"{user}{_JSON_INSTRUCTION}{schema_blob}"
        result: dict | None = None
        last_errors: list[str] = []
        for attempt in range(2):
            prompt = user_full
            if attempt == 1:
                prompt = f"{user_full}\n\nYour previous reply was invalid: {last_errors}. Return ONLY the corrected JSON object."
            text = self._run_cli(system=system, user=prompt, model=use_model)
            try:
                candidate = _extract_json_object(text)
            except json.JSONDecodeError:
                last_errors = ["output was not valid JSON"]
                continue
            last_errors = schema_errors(candidate, json_schema)
            if not last_errors:
                result = candidate
                break
        if result is None:
            raise RuntimeError(f"claude -p output failed schema validation after retry: {last_errors}")

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def make_llm(
    backend: str,
    *,
    model: str = DEFAULT_MODEL,
    cache_dir: str | Path | None = None,
    timeout: int | None = None,
) -> LLMClient:
    """Construct an :class:`LLMClient` for the chosen backend.

    Parameters
    ----------
    backend
        ``"subscription"`` → :class:`ClaudeCliClient` (Claude Max via ``claude -p``, zero API spend);
        ``"api"`` → :class:`AnthropicClient` (paid Messages API, opt-in).
    model
        Model id / alias.
    cache_dir
        Shared disk cache directory.
    timeout
        Per-call subprocess timeout in seconds for the subscription backend (ignored for ``api``).
        ``None`` keeps the client default.

    Returns
    -------
    LLMClient
        The backend client.
    """
    if backend == "subscription":
        kw = {"timeout": timeout} if timeout is not None else {}
        return ClaudeCliClient(model=model, cache_dir=cache_dir, **kw)
    if backend == "api":
        return AnthropicClient(model=model, cache_dir=cache_dir)
    raise ValueError(f"Unknown backend {backend!r} (expected 'subscription' or 'api').")
