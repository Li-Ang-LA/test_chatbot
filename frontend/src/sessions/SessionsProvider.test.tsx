import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import { SessionsProvider } from './SessionsProvider';
import { Sidebar } from '../sidebar/Sidebar';
import { SessionChat } from '../chat/SessionChat';
import { AuthContext } from '../auth/context';
import type { AuthContextValue } from '../auth/context';

type FetchArgs = Parameters<typeof fetch>;
type Session = {
  id: number;
  title: string;
  claude_session_id: null;
  system_prompt: null;
  created_at: string;
  updated_at: string;
};

const fakeAuth: AuthContextValue = {
  user: {
    id: 1,
    email: 'a@b.co',
    username: 'alice',
    created_at: '2026-01-01T00:00:00Z',
  },
  status: 'authenticated',
  login: async () => {},
  signup: async () => {},
  logout: async () => {},
  refresh: async () => {},
};

function makeSession(id: number, title: string, updated_at: string): Session {
  return {
    id,
    title,
    claude_session_id: null,
    system_prompt: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at,
  };
}

type Fixtures = {
  /** Initial server-side list returned for the very first GET /sessions. */
  initialList: Session[];
  /** History returned for GET /sessions/:id (unused fields can be empty). */
  histories?: Record<number, Session & { messages: unknown[] }>;
  /**
   * Mutates the fixtures when the stream completes server-side. Lets a test
   * simulate the backend-side title bump + updated_at refresh that the
   * Sidebar refetches after `done`.
   */
  onStreamDone?: (
    state: { list: Session[] },
    sessionId: number,
    content: string,
  ) => void;
};

function mountFetch(fixtures: Fixtures) {
  const state = { list: [...fixtures.initialList] };
  const calls: { url: string; method: string }[] = [];

  const fetchMock = vi.fn(async (...args: FetchArgs) => {
    const [input, init] = args;
    const url = typeof input === 'string' ? input : (input as Request).url;
    const method = (init?.method ?? 'GET').toUpperCase();
    calls.push({ url, method });

    if (url.endsWith('/sessions') && method === 'GET') {
      // Backend orders by updated_at desc, id desc — mirror that here.
      const sorted = [...state.list].sort((a, b) => {
        const cmp = b.updated_at.localeCompare(a.updated_at);
        return cmp !== 0 ? cmp : b.id - a.id;
      });
      return new Response(JSON.stringify(sorted), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const getOne = url.match(/\/sessions\/(\d+)$/);
    if (getOne && method === 'GET') {
      const id = Number(getOne[1]);
      const detail = fixtures.histories?.[id];
      if (!detail) {
        return new Response(
          JSON.stringify({
            ...makeSession(id, 'Session', '2026-01-01T00:00:00Z'),
            messages: [],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify(detail), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const post = url.match(/\/sessions\/(\d+)\/messages$/);
    if (post && method === 'POST') {
      const id = Number(post[1]);
      const content = init?.body
        ? (JSON.parse(init.body as string) as { content: string }).content
        : '';
      const body = new ReadableStream<Uint8Array>({
        async start(controller) {
          const encoder = new TextEncoder();
          controller.enqueue(
            encoder.encode('event: delta\ndata: {"text": "ok"}\n\n'),
          );
          controller.enqueue(
            encoder.encode('event: done\ndata: {"text": "ok"}\n\n'),
          );
          // Simulate the server-side mutations that happen inside the stream.
          fixtures.onStreamDone?.(state, id, content);
          controller.close();
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
  return { fetchMock, calls, state };
}

function renderApp(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthContext.Provider value={fakeAuth}>
        <SessionsProvider>
          <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1 }}>
              <Routes>
                <Route path="/c/:sessionId" element={<ChatRoute />} />
              </Routes>
            </main>
          </div>
        </SessionsProvider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

function ChatRoute() {
  // Inline route so the test doesn't depend on AppShell's wrapper.
  const { sessionId } = useParams<{ sessionId: string }>();
  const sid = Number(sessionId);
  return <SessionChat key={sid} sessionId={sid} />;
}

beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Live sidebar updates (M4.3)', () => {
  it('retitles a "New chat" sidebar entry after the first user message', async () => {
    mountFetch({
      initialList: [
        makeSession(1, 'New chat', '2026-01-01T00:00:00Z'),
        makeSession(2, 'Older convo', '2025-12-31T00:00:00Z'),
      ],
      histories: {
        1: {
          ...makeSession(1, 'New chat', '2026-01-01T00:00:00Z'),
          messages: [],
        },
      },
      onStreamDone(state, sid, content) {
        // Server-side: title was bumped at user-message persist, updated_at
        // again at message_done. Reflect both here.
        state.list = state.list.map((s) =>
          s.id === sid
            ? {
                ...s,
                title: content.slice(0, 60),
                updated_at: '2026-02-01T00:00:00Z',
              }
            : s,
        );
      },
    });

    const user = userEvent.setup();
    renderApp('/c/1');

    // Sidebar populated from initial GET /sessions.
    await screen.findByRole('button', { name: 'New chat' });
    // Wait for the chat to finish loading the (empty) message history.
    await screen.findByRole('region', { name: /start a new chat/i });

    // Send the first message in session 1.
    const input = screen.getByRole('textbox', { name: /message/i });
    await user.type(input, 'Plan a trip to Kyoto');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    // Optimistic update: the sidebar entry retitles immediately.
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Plan a trip to Kyoto' }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole('button', { name: 'New chat' }),
    ).not.toBeInTheDocument();
  });

  it('floats the just-active session to the top of the sidebar list', async () => {
    mountFetch({
      initialList: [
        makeSession(1, 'Stale chat', '2026-01-01T00:00:00Z'),
        makeSession(2, 'Most recent', '2026-01-10T00:00:00Z'),
        makeSession(3, 'Middle', '2026-01-05T00:00:00Z'),
      ],
      histories: {
        1: {
          ...makeSession(1, 'Stale chat', '2026-01-01T00:00:00Z'),
          messages: [],
        },
      },
      onStreamDone(state, sid) {
        state.list = state.list.map((s) =>
          s.id === sid ? { ...s, updated_at: '2026-02-15T00:00:00Z' } : s,
        );
      },
    });

    const user = userEvent.setup();
    const { container } = renderApp('/c/1');

    // Initial order is Most recent, Middle, Stale chat (descending updated_at).
    await screen.findByRole('button', { name: 'Stale chat' });
    const initialOrder = within(container)
      .getAllByRole('button')
      .map((b) => b.textContent)
      .filter((t) => ['Most recent', 'Middle', 'Stale chat'].includes(t ?? ''));
    expect(initialOrder).toEqual(['Most recent', 'Middle', 'Stale chat']);

    // Send a message in the stale session — sidebar should bubble it to top.
    const input = screen.getByRole('textbox', { name: /message/i });
    await user.type(input, 'wake up');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await waitFor(() => {
      const order = within(container)
        .getAllByRole('button')
        .map((b) => b.textContent)
        .filter((t) =>
          ['Most recent', 'Middle', 'Stale chat', 'wake up'].includes(t ?? ''),
        );
      // Optimistic bump: stale chat (now retitled to 'wake up' since it was
      // 'Stale chat' — wait no, 'Stale chat' is not 'New chat' so title sticks)
      expect(order[0]).toBe('Stale chat');
    });
  });
});
