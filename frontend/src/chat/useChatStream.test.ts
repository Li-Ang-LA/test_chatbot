import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useChatStream } from './useChatStream';

type FetchArgs = Parameters<typeof fetch>;

type MockConfig = {
  sseChunks: string[];
  hang?: boolean;
  history?: Array<{
    id: number;
    role: 'user' | 'assistant';
    content: string;
    created_at: string;
  }>;
  /** SSE chunks returned from GET /sessions/1/messages/stream. Omit (or
   * leave empty) to simulate "no active turn" — stream closes immediately. */
  reattachChunks?: string[];
};

type MockRecord = {
  fetchMock: ReturnType<typeof vi.fn>;
  postSignal: { current: AbortSignal | null };
  reattachSignal: { current: AbortSignal | null };
};

function mountFetch({
  sseChunks,
  hang = false,
  history = [],
  reattachChunks = [],
}: MockConfig): MockRecord {
  const postSignal: { current: AbortSignal | null } = { current: null };
  const reattachSignal: { current: AbortSignal | null } = { current: null };

  const fetchMock = vi.fn(async (...args: FetchArgs) => {
    const [input, init] = args;
    const url = typeof input === 'string' ? input : (input as Request).url;

    if (url.endsWith('/sessions/1') && (init?.method ?? 'GET') === 'GET') {
      return new Response(
        JSON.stringify({
          id: 1,
          title: 'T',
          claude_session_id: null,
          system_prompt: null,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          messages: history,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }

    if (
      url.endsWith('/sessions/1/messages/stream') &&
      (init?.method ?? 'GET') === 'GET'
    ) {
      reattachSignal.current = init?.signal ?? null;
      const body = new ReadableStream<Uint8Array>({
        async start(controller) {
          const encoder = new TextEncoder();
          for (const chunk of reattachChunks) {
            controller.enqueue(encoder.encode(chunk));
            await new Promise((resolve) => setTimeout(resolve, 0));
          }
          controller.close();
        },
        cancel() {
          // consumer bailed
        },
      });
      return new Response(body, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }

    if (url.endsWith('/sessions/1/messages') && init?.method === 'POST') {
      postSignal.current = init?.signal ?? null;
      const body = new ReadableStream<Uint8Array>({
        async start(controller) {
          const encoder = new TextEncoder();
          for (const chunk of sseChunks) {
            controller.enqueue(encoder.encode(chunk));
            await new Promise((resolve) => setTimeout(resolve, 0));
          }
          if (!hang) controller.close();
        },
        cancel() {
          // stream cancelled by consumer (e.g. abort propagation)
        },
      });
      return new Response(body, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }

    return new Response(null, { status: 404 });
  });

  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, postSignal, reattachSignal };
}

beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useChatStream', () => {
  it('streams deltas and finalizes the assistant message on done', async () => {
    mountFetch({
      sseChunks: [
        'event: delta\ndata: {"text": "Hel"}\n\n',
        'event: delta\ndata: {"text": "lo"}\n\n',
        'event: done\ndata: {"text": "Hello"}\n\n',
      ],
    });

    const { result } = renderHook(() => useChatStream(1));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.send('hi there');
    });

    const roles = result.current.messages.map((m) => m.role);
    expect(roles).toEqual(['user', 'assistant']);
    expect(result.current.messages[0].content).toBe('hi there');
    expect(result.current.messages[1].content).toBe('Hello');
    expect(result.current.error).toBeNull();
    expect(result.current.isSending).toBe(false);
  });

  it('exposes an error state and stops streaming on an error event', async () => {
    mountFetch({
      sseChunks: [
        'event: delta\ndata: {"text": "partial"}\n\n',
        'event: error\ndata: {"error": "claude blew up"}\n\n',
      ],
    });

    const { result } = renderHook(() => useChatStream(1));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.send('hi');
    });

    expect(result.current.error).toBe('claude blew up');
    // user message persisted; assistant not finalized; no streaming message visible
    const roles = result.current.messages.map((m) => m.role);
    expect(roles).toEqual(['user']);
    expect(result.current.isSending).toBe(false);
  });

  it('aborts the in-flight fetch when unmounted mid-stream', async () => {
    const { postSignal } = mountFetch({
      sseChunks: ['event: delta\ndata: {"text": "…"}\n\n'],
      hang: true,
    });

    const { result, unmount } = renderHook(() => useChatStream(1));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      void result.current.send('hi');
    });
    await waitFor(() => expect(postSignal.current).not.toBeNull());
    expect(postSignal.current!.aborted).toBe(false);

    unmount();

    expect(postSignal.current!.aborted).toBe(true);
  });

  it('loads persisted history on mount', async () => {
    mountFetch({
      sseChunks: [],
      history: [
        {
          id: 10,
          role: 'user',
          content: 'past question',
          created_at: '2026-01-01T00:00:00Z',
        },
        {
          id: 11,
          role: 'assistant',
          content: 'past answer',
          created_at: '2026-01-01T00:00:01Z',
        },
      ],
    });

    const { result } = renderHook(() => useChatStream(1));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.messages.map((m) => m.content)).toEqual([
      'past question',
      'past answer',
    ]);
  });

  it('reattaches to an in-flight turn and finalizes on done', async () => {
    mountFetch({
      sseChunks: [],
      history: [
        {
          id: 10,
          role: 'user',
          content: 'still running?',
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
      // Server replays accumulated buffer, sends one more delta, then done.
      reattachChunks: [
        'event: delta\ndata: {"text": "Par"}\n\n',
        'event: delta\ndata: {"text": "tial"}\n\n',
        'event: done\ndata: {"text": "Partial reply"}\n\n',
      ],
    });

    const { result } = renderHook(() => useChatStream(1));

    await waitFor(() =>
      expect(
        result.current.messages.map((m) => `${m.role}:${m.content}`),
      ).toEqual(['user:still running?', 'assistant:Partial reply']),
    );
    expect(result.current.error).toBeNull();
    // After done, streaming state cleared and input is no longer locked.
    expect(result.current.isSending).toBe(false);
  });

  it('aborts the reattach fetch on unmount', async () => {
    const { reattachSignal } = mountFetch({
      sseChunks: [],
      history: [],
      // Include an event so the body isn't immediately closed — we want
      // the SSE reader to still be active when we unmount.
      reattachChunks: ['event: delta\ndata: {"text": "live"}\n\n'],
    });

    const { result, unmount } = renderHook(() => useChatStream(1));
    await waitFor(() => expect(reattachSignal.current).not.toBeNull());
    expect(reattachSignal.current!.aborted).toBe(false);

    unmount();

    expect(reattachSignal.current!.aborted).toBe(true);
    // Suppress unused-var lint: result is only here to keep the hook mounted
    // before unmount.
    void result;
  });
});
