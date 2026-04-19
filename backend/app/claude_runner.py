"""Wraps the `claude` CLI so the backend can spawn a per-session subprocess,
stream its stream-json output, and surface timeouts/errors as StreamEvents.

The wrapper never interpolates user input into a shell string — all arguments
are passed as an argv list to `asyncio.create_subprocess_exec`.

CLI usage (for manual smoke-testing against a locally authenticated CLI):

    python -m app.claude_runner "hello"

This requires the host to already be logged into Claude Code (`claude login`).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 180.0
CLAUDE_BIN = os.environ.get("CLAUDE_CLI_BIN", "claude")

EventType = Literal["text_delta", "message_done", "error"]


@dataclass(frozen=True)
class StreamEvent:
    type: EventType
    text: str | None = None
    error: str | None = None


class ClaudeRunnerError(RuntimeError):
    """Raised when the Claude CLI cannot be driven to produce a usable response."""


def _build_start_argv(system_prompt: str | None) -> list[str]:
    argv: list[str] = [
        CLAUDE_BIN,
        "--print",
        "<noop init>",
        "--output-format",
        "json",
    ]
    if system_prompt:
        argv += ["--append-system-prompt", system_prompt]
    return argv


def _build_send_argv(claude_session_id: str, prompt: str) -> list[str]:
    return [
        CLAUDE_BIN,
        "-p",
        prompt,
        "--resume",
        claude_session_id,
        "--output-format",
        "stream-json",
        "--verbose",
        # Required for the CLI to emit stream_event / content_block_delta
        # records; without it we only get a single terminal assistant block.
        "--include-partial-messages",
    ]


async def start_session(
    system_prompt: str | None = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> str:
    """Initialize a new Claude Code session and return its session_id."""
    argv = _build_start_argv(system_prompt)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError as e:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        raise ClaudeRunnerError(f"start_session timed out after {timeout_s}s") from e

    if proc.returncode != 0:
        msg = stderr.decode(errors="replace").strip() or "unknown error"
        raise ClaudeRunnerError(f"claude exited {proc.returncode}: {msg}")

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise ClaudeRunnerError(f"invalid JSON from claude CLI: {e}") from e

    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    if not isinstance(session_id, str) or not session_id:
        raise ClaudeRunnerError("claude response missing session_id")
    return session_id


ParsedKind = Literal["delta", "assistant_full", "done"]


def _parse_stream_line(line: bytes) -> tuple[ParsedKind, StreamEvent] | None:
    """Parse one NDJSON line from `claude --output-format stream-json --verbose`.

    Returns `(kind, event)` where `kind` tells the caller how to treat the
    event, or None for lines we don't need to surface. Malformed JSON is
    logged and dropped rather than crashing the iterator.

    The CLI interleaves `stream_event` records (with `content_block_delta`
    fragments) during generation and then emits one `assistant` summary
    containing the full text. We surface:

    - ("delta",  text_delta)  — an incremental fragment from stream_event
    - ("assistant_full", text_delta) — the final summary; callers can use
      this as a fallback when no incremental fragments were seen
    - ("done", message_done) — the result terminator
    """
    stripped = line.strip()
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        log.warning("dropping malformed stream-json line: %r", stripped[:200])
        return None
    if not isinstance(obj, dict):
        return None

    kind = obj.get("type")

    if kind == "stream_event":
        event = obj.get("event") or {}
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if isinstance(text, str) and text:
                    return "delta", StreamEvent(type="text_delta", text=text)
        return None

    if kind == "assistant":
        message = obj.get("message") or {}
        content = message.get("content") or []
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "".join(parts)
        if text:
            return "assistant_full", StreamEvent(type="text_delta", text=text)
        return None

    if kind == "result":
        return "done", StreamEvent(type="message_done")

    return None


async def send_message(
    claude_session_id: str,
    prompt: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> AsyncIterator[StreamEvent]:
    """Stream events from a single turn of the resumed Claude session."""
    argv = _build_send_argv(claude_session_id, prompt)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    timed_out = False
    saw_delta = False

    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                timed_out = True
                break
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                timed_out = True
                break
            if not line:
                break  # EOF
            parsed = _parse_stream_line(line)
            if parsed is None:
                continue
            kind, ev = parsed
            if kind == "delta":
                saw_delta = True
                yield ev
            elif kind == "assistant_full":
                # Only surface the summary when the CLI didn't already give
                # us incremental fragments — otherwise clients would see the
                # full reply twice.
                if not saw_delta:
                    yield ev
            else:  # "done"
                yield ev

        if timed_out:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            yield StreamEvent(
                type="error",
                error=f"claude timed out after {timeout_s}s",
            )
            return

        await proc.wait()
        if proc.returncode not in (0, None):
            stderr_bytes = await proc.stderr.read()
            detail = stderr_bytes.decode(errors="replace").strip()
            yield StreamEvent(
                type="error",
                error=detail or f"claude exited {proc.returncode}",
            )
    finally:
        if proc.returncode is None:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()


async def _cli(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].strip():
        print("usage: python -m app.claude_runner <prompt>", file=sys.stderr)
        return 2
    prompt = argv[1]
    try:
        session_id = await start_session()
    except ClaudeRunnerError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1

    had_text = False
    async for ev in send_message(session_id, prompt):
        if ev.type == "text_delta" and ev.text:
            sys.stdout.write(ev.text)
            sys.stdout.flush()
            had_text = True
        elif ev.type == "error":
            print(f"\n[error] {ev.error}", file=sys.stderr)
            return 1
        elif ev.type == "message_done":
            sys.stdout.write("\n")
            sys.stdout.flush()
    return 0 if had_text else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(asyncio.run(_cli(sys.argv)))
