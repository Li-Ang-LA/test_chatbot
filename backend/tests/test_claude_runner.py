import asyncio
import json
from collections.abc import Iterable

import pytest

from app import claude_runner
from app.claude_runner import (
    ClaudeRunnerError,
    _build_send_argv,
    _build_start_argv,
    _parse_stream_line,
    send_message,
    start_session,
)

# ---------- pure argv-builder tests ---------------------------------------


def test_start_argv_without_system_prompt():
    argv = _build_start_argv(None)
    assert argv == [
        claude_runner.CLAUDE_BIN,
        "--print",
        "<noop init>",
        "--output-format",
        "json",
    ]


def test_start_argv_with_system_prompt_passthrough():
    argv = _build_start_argv("Be terse.")
    assert argv[-2:] == ["--append-system-prompt", "Be terse."]


def test_send_argv_passes_prompt_and_resume():
    argv = _build_send_argv("session-abc", "hello there")
    assert argv == [
        claude_runner.CLAUDE_BIN,
        "-p",
        "hello there",
        "--resume",
        "session-abc",
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def test_send_argv_does_not_shell_interpolate_prompt():
    # Critical: special shell characters must pass through as a single argv entry,
    # not be interpreted by any shell.
    argv = _build_send_argv("sid", "rm -rf / && echo $HOME")
    assert argv[2] == "rm -rf / && echo $HOME"


# ---------- parsing tests -------------------------------------------------


def test_parse_assistant_text_block_yields_delta():
    line = json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello"}]},
        }
    ).encode()
    ev = _parse_stream_line(line)
    assert ev is not None and ev.type == "text_delta" and ev.text == "Hello"


def test_parse_result_line_yields_message_done():
    ev = _parse_stream_line(b'{"type":"result","subtype":"success"}')
    assert ev is not None and ev.type == "message_done"


def test_parse_malformed_line_returns_none(caplog):
    with caplog.at_level("WARNING"):
        ev = _parse_stream_line(b"not-json")
    assert ev is None
    assert any("malformed" in r.message for r in caplog.records)


def test_parse_ignores_unknown_types():
    assert _parse_stream_line(b'{"type":"system","subtype":"init"}') is None


# ---------- subprocess-mocked integration tests ---------------------------


class _FakeStream:
    """Minimal stand-in for asyncio.StreamReader.readline()."""

    def __init__(self, lines: Iterable[bytes], *, hang: bool = False) -> None:
        self._lines = list(lines)
        self._hang = hang

    async def readline(self) -> bytes:
        if self._hang:
            await asyncio.sleep(3600)  # effectively blocks until timeout
        if not self._lines:
            return b""
        return self._lines.pop(0)

    async def read(self) -> bytes:
        return b"".join(self._lines)


class _FakeProcess:
    def __init__(
        self,
        *,
        stdout_lines: Iterable[bytes] = (),
        stderr_bytes: bytes = b"",
        stdout_bytes: bytes = b"",
        returncode: int | None = 0,
        hang_stdout: bool = False,
    ) -> None:
        self.stdout = _FakeStream(stdout_lines, hang=hang_stdout)
        self.stderr = _FakeStream([stderr_bytes] if stderr_bytes else [])
        self._stdout_bytes = stdout_bytes
        self._stderr_bytes = stderr_bytes
        self._rc = returncode
        self.returncode: int | None = None
        self.killed = False

    async def wait(self) -> int | None:
        self.returncode = self._rc
        return self._rc

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def communicate(self) -> tuple[bytes, bytes]:
        self.returncode = self._rc
        return self._stdout_bytes, self._stderr_bytes


def _patch_exec(monkeypatch, fake: _FakeProcess, captured: dict):
    async def fake_create_subprocess_exec(*argv, stdout=None, stderr=None):
        captured["argv"] = list(argv)
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        return fake

    monkeypatch.setattr(
        claude_runner.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )


# ---------- start_session --------------------------------------------------


async def test_start_session_builds_argv_and_parses_session_id(monkeypatch):
    fake = _FakeProcess(stdout_bytes=json.dumps({"session_id": "s-xyz"}).encode())
    captured: dict = {}
    _patch_exec(monkeypatch, fake, captured)

    sid = await start_session("Be concise.")

    assert sid == "s-xyz"
    assert captured["argv"][0] == claude_runner.CLAUDE_BIN
    assert "--output-format" in captured["argv"]
    assert "--append-system-prompt" in captured["argv"]
    assert "Be concise." in captured["argv"]


async def test_start_session_raises_on_nonzero_exit(monkeypatch):
    fake = _FakeProcess(returncode=1, stderr_bytes=b"boom")
    _patch_exec(monkeypatch, fake, {})

    with pytest.raises(ClaudeRunnerError, match="boom"):
        await start_session()


async def test_start_session_raises_on_missing_session_id(monkeypatch):
    fake = _FakeProcess(stdout_bytes=json.dumps({"model": "claude"}).encode())
    _patch_exec(monkeypatch, fake, {})

    with pytest.raises(ClaudeRunnerError, match="session_id"):
        await start_session()


# ---------- send_message ---------------------------------------------------


def _assistant_line(text: str) -> bytes:
    return (
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": text}]},
            }
        )
        + "\n"
    ).encode()


def _result_line() -> bytes:
    return b'{"type":"result","subtype":"success"}\n'


async def test_send_message_yields_deltas_then_done(monkeypatch):
    fake = _FakeProcess(
        stdout_lines=[
            _assistant_line("Hello"),
            _assistant_line(" world"),
            _result_line(),
        ]
    )
    captured: dict = {}
    _patch_exec(monkeypatch, fake, captured)

    events = [ev async for ev in send_message("sid-1", "hi")]
    assert [ev.type for ev in events] == ["text_delta", "text_delta", "message_done"]
    assert "".join(ev.text or "" for ev in events) == "Hello world"
    # argv sanity
    assert "--resume" in captured["argv"]
    assert "sid-1" in captured["argv"]
    assert "hi" in captured["argv"]


async def test_send_message_skips_malformed_json_lines(monkeypatch, caplog):
    fake = _FakeProcess(
        stdout_lines=[
            b"not-json\n",
            _assistant_line("ok"),
            _result_line(),
        ]
    )
    _patch_exec(monkeypatch, fake, {})

    with caplog.at_level("WARNING"):
        events = [ev async for ev in send_message("sid", "hi")]

    assert [ev.type for ev in events] == ["text_delta", "message_done"]
    assert events[0].text == "ok"
    assert any("malformed" in r.message for r in caplog.records)


async def test_send_message_times_out_and_kills(monkeypatch):
    fake = _FakeProcess(hang_stdout=True, returncode=None)
    _patch_exec(monkeypatch, fake, {})

    events = [ev async for ev in send_message("sid", "hi", timeout_s=0.05)]
    assert len(events) == 1
    assert events[0].type == "error"
    assert "timed out" in (events[0].error or "")
    assert fake.killed is True


async def test_send_message_emits_error_on_nonzero_exit(monkeypatch):
    fake = _FakeProcess(
        stdout_lines=[_assistant_line("partial")],
        stderr_bytes=b"oops",
        returncode=2,
    )
    _patch_exec(monkeypatch, fake, {})

    events = [ev async for ev in send_message("sid", "hi")]
    assert [ev.type for ev in events] == ["text_delta", "error"]
    assert "oops" in (events[-1].error or "")
