import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { SessionChat } from './SessionChat';
import { SessionsProvider } from '../sessions/SessionsProvider';

type FetchArgs = Parameters<typeof fetch>;
type PersistedMsg = {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
};

type SessionFixture = {
  history: PersistedMsg[];
  /** If set, a POST to this session's /messages returns a stream that never closes. */
  hangStream?: boolean;
};

function mountFetch(sessions: Record<number, SessionFixture>) {
  const getCalls: number[] = [];
  const postSignals = new Map<number, AbortSignal>();

  const fetchMock = vi.fn(async (...args: FetchArgs) => {
    const [input, init] = args;
    const url = typeof input === 'string' ? input : (input as Request).url;
    const method = (init?.method ?? 'GET').toUpperCase();

    const getMatch = url.match(/\/sessions\/(\d+)$/);
    if (getMatch && method === 'GET') {
      const id = Number(getMatch[1]);
      getCalls.push(id);
      const fix = sessions[id];
      if (!fix) return new Response(null, { status: 404 });
      return new Response(
        JSON.stringify({
          id,
          title: `Session ${id}`,
          claude_session_id: null,
          system_prompt: null,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          messages: fix.history,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }

    const streamMatch = url.match(/\/sessions\/(\d+)\/messages\/stream$/);
    if (streamMatch && method === 'GET') {
      // No active turn in these tests — close the SSE immediately so the
      // hook just falls through to the persisted-history state.
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.close();
        },
      });
      return new Response(body, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }

    const postMatch = url.match(/\/sessions\/(\d+)\/messages$/);
    if (postMatch && method === 'POST') {
      const id = Number(postMatch[1]);
      if (init?.signal) postSignals.set(id, init.signal);
      const fix = sessions[id];
      const hang = fix?.hangStream ?? false;
      const body = new ReadableStream<Uint8Array>({
        async start(controller) {
          const encoder = new TextEncoder();
          controller.enqueue(
            encoder.encode('event: delta\ndata: {"text": "par"}\n\n'),
          );
          if (!hang) {
            controller.enqueue(
              encoder.encode('event: done\ndata: {"text": "par"}\n\n'),
            );
            controller.close();
          }
        },
        cancel() {
          // SSE consumer aborted the fetch; nothing to clean up here.
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
  return { fetchMock, getCalls, postSignals };
}

function Host({ sessionId }: { sessionId: number }) {
  return (
    <SessionsProvider>
      <SessionChat key={sessionId} sessionId={sessionId} />
    </SessionsProvider>
  );
}

beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('SessionChat per-session isolation (M4.2)', () => {
  it("aborts session A's in-flight stream when navigating to session B, and shows only B's history", async () => {
    const { postSignals, getCalls } = mountFetch({
      1: {
        history: [
          {
            id: 101,
            role: 'user',
            content: 'A past question',
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        hangStream: true,
      },
      2: {
        history: [
          {
            id: 201,
            role: 'user',
            content: 'B past question',
            created_at: '2026-01-01T00:00:00Z',
          },
          {
            id: 202,
            role: 'assistant',
            content: 'B past answer',
            created_at: '2026-01-01T00:00:01Z',
          },
        ],
      },
    });

    function Wrapper() {
      const [sid, setSid] = useState(1);
      return (
        <div>
          <button type="button" onClick={() => setSid(2)}>
            go to B
          </button>
          <Host sessionId={sid} />
        </div>
      );
    }

    const user = userEvent.setup();
    render(<Wrapper />);
    await waitFor(() =>
      expect(screen.getByText('A past question')).toBeInTheDocument(),
    );

    // Send a message in A; the mock stream hangs, so the fetch is in flight.
    const input = screen.getByRole('textbox', { name: /message/i });
    await user.type(input, 'hello A');
    await user.click(screen.getByRole('button', { name: /^send$/i }));
    await waitFor(() => expect(postSignals.get(1)).toBeDefined());
    expect(postSignals.get(1)!.aborted).toBe(false);

    // Navigate to session B mid-stream — key change forces SessionChat to unmount
    // which fires the hook's cleanup and aborts A's fetch.
    await user.click(screen.getByRole('button', { name: /go to b/i }));

    expect(postSignals.get(1)!.aborted).toBe(true);

    await waitFor(() =>
      expect(screen.getByText('B past question')).toBeInTheDocument(),
    );
    // B shows only B's messages — nothing from A leaks across.
    expect(screen.queryByText('A past question')).not.toBeInTheDocument();
    expect(screen.queryByText('hello A')).not.toBeInTheDocument();
    expect(screen.getByText('B past answer')).toBeInTheDocument();

    // Sanity: history was fetched once per session (no crosstalk via cache).
    expect(getCalls).toEqual([1, 2]);
  });

  it("refetches session A's persisted history when navigating back", async () => {
    let aHistory: PersistedMsg[] = [
      {
        id: 101,
        role: 'user',
        content: 'hello A',
        created_at: '2026-01-01T00:00:00Z',
      },
    ];
    const sessions: Record<number, SessionFixture> = {
      1: {
        get history() {
          return aHistory;
        },
      } as SessionFixture,
      2: { history: [] },
    };
    // Proxy to surface the getter through fetch's JSON snapshot.
    const { getCalls } = mountFetch(
      new Proxy(sessions, {
        get(t, k) {
          return (t as Record<string, SessionFixture>)[k as string];
        },
      }) as Record<number, SessionFixture>,
    );

    function Wrapper() {
      const [sid, setSid] = useState(1);
      return (
        <div>
          <button type="button" onClick={() => setSid(2)}>
            to B
          </button>
          <button type="button" onClick={() => setSid(1)}>
            to A
          </button>
          <Host sessionId={sid} />
        </div>
      );
    }

    const user = userEvent.setup();
    const { container } = render(<Wrapper />);
    await waitFor(() =>
      expect(screen.getByText('hello A')).toBeInTheDocument(),
    );

    // Simulate that while we were away, session A's stream completed on the server.
    aHistory = [
      ...aHistory,
      {
        id: 102,
        role: 'assistant',
        content: 'finalized reply',
        created_at: '2026-01-01T00:00:05Z',
      },
    ];

    await user.click(screen.getByRole('button', { name: /to b/i }));
    await waitFor(() =>
      expect(getCalls.filter((id) => id === 2)).toHaveLength(1),
    );

    await user.click(screen.getByRole('button', { name: /to a/i }));

    await waitFor(() =>
      expect(screen.getByText('finalized reply')).toBeInTheDocument(),
    );
    // History was re-requested for A on return (not served from stale state).
    expect(getCalls.filter((id) => id === 1)).toHaveLength(2);
    // Both A messages visible; no B state lingered.
    const region = within(container).getByRole('region', {
      name: /chat conversation/i,
    });
    expect(within(region).getByText('hello A')).toBeInTheDocument();
    expect(within(region).getByText('finalized reply')).toBeInTheDocument();
  });
});
