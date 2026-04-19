import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { AuthContext } from '../auth/context';
import type { AuthContextValue } from '../auth/context';
import { SessionsProvider } from '../sessions/SessionsProvider';

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

type FakeSession = {
  id: number;
  title: string;
  claude_session_id: null;
  system_prompt: null;
  created_at: string;
  updated_at: string;
};

function makeSession(id: number, title: string): FakeSession {
  const iso = `2026-01-${String(id).padStart(2, '0')}T00:00:00Z`;
  return {
    id,
    title,
    claude_session_id: null,
    system_prompt: null,
    created_at: iso,
    updated_at: iso,
  };
}

function RoutePath() {
  const { pathname } = useLocation();
  return <div data-testid="route-path">{pathname}</div>;
}

function renderSidebar(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthContext.Provider value={fakeAuth}>
        <SessionsProvider>
          <Routes>
            <Route
              path="/"
              element={
                <>
                  <Sidebar />
                  <RoutePath />
                </>
              }
            />
            <Route
              path="/c/:sessionId"
              element={
                <>
                  <Sidebar />
                  <RoutePath />
                </>
              }
            />
          </Routes>
        </SessionsProvider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Sidebar', () => {
  it('collapse toggles data-collapsed and localStorage', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse([]));

    const user = userEvent.setup();
    renderSidebar();

    const aside = await screen.findByRole('complementary', {
      name: /sidebar/i,
    });
    expect(aside).toHaveAttribute('data-collapsed', 'false');
    expect(window.localStorage.getItem('sidebar:collapsed')).toBe('0');

    await user.click(screen.getByRole('button', { name: /collapse sidebar/i }));

    const collapsedAside = screen.getByRole('complementary', {
      name: /sidebar/i,
    });
    expect(collapsedAside).toHaveAttribute('data-collapsed', 'true');
    expect(window.localStorage.getItem('sidebar:collapsed')).toBe('1');

    await user.click(screen.getByRole('button', { name: /expand sidebar/i }));
    expect(
      screen.getByRole('complementary', { name: /sidebar/i }),
    ).toHaveAttribute('data-collapsed', 'false');
    expect(window.localStorage.getItem('sidebar:collapsed')).toBe('0');
  });

  it('clicking + creates a session and navigates to /c/:id', async () => {
    const calls: Array<{ url: string; method: string; body: unknown }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      const method = (init?.method ?? 'GET').toUpperCase();
      const body = init?.body ? JSON.parse(init.body as string) : null;
      calls.push({ url, method, body });
      if (url.endsWith('/sessions') && method === 'GET')
        return jsonResponse([]);
      if (url.endsWith('/sessions') && method === 'POST') {
        return jsonResponse(makeSession(42, 'New chat'), 201);
      }
      return new Response(null, { status: 404 });
    });

    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByRole('button', { name: /new session/i }));

    await waitFor(() =>
      expect(screen.getByTestId('route-path')).toHaveTextContent('/c/42'),
    );
    expect(
      calls.some((c) => c.url.endsWith('/sessions') && c.method === 'POST'),
    ).toBe(true);
    // New session appears in the list too.
    expect(
      screen.getByRole('button', { name: 'New chat' }),
    ).toBeInTheDocument();
  });

  it('rename inline-edit fires PATCH with the new title', async () => {
    const patchCalls: Array<{ url: string; body: unknown }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      const method = (init?.method ?? 'GET').toUpperCase();
      if (url.endsWith('/sessions') && method === 'GET') {
        return jsonResponse([makeSession(7, 'Old title')]);
      }
      if (url.endsWith('/sessions/7') && method === 'PATCH') {
        patchCalls.push({ url, body: JSON.parse(init!.body as string) });
        return jsonResponse({ ...makeSession(7, 'Trip planning') });
      }
      return new Response(null, { status: 404 });
    });

    const user = userEvent.setup();
    renderSidebar();

    await screen.findByRole('button', { name: 'Old title' });
    await user.click(
      screen.getByRole('button', { name: /actions for old title/i }),
    );
    await user.click(screen.getByRole('menuitem', { name: /rename/i }));

    const input = screen.getByRole('textbox', { name: /rename session/i });
    await user.clear(input);
    await user.type(input, 'Trip planning{Enter}');

    await waitFor(() => expect(patchCalls).toHaveLength(1));
    expect(patchCalls[0].url).toMatch(/\/sessions\/7$/);
    expect(patchCalls[0].body).toEqual({ title: 'Trip planning' });
    expect(
      await screen.findByRole('button', { name: 'Trip planning' }),
    ).toBeInTheDocument();
  });

  it('row menu closes on Escape and on outside click', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      const method = (init?.method ?? 'GET').toUpperCase();
      if (url.endsWith('/sessions') && method === 'GET')
        return jsonResponse([makeSession(3, 'Test chat')]);
      return new Response(null, { status: 404 });
    });

    const user = userEvent.setup();
    renderSidebar();

    await screen.findByRole('button', { name: 'Test chat' });

    // Open via click, close via Escape.
    await user.click(
      screen.getByRole('button', { name: /actions for test chat/i }),
    );
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    // Open again, click outside → close.
    await user.click(
      screen.getByRole('button', { name: /actions for test chat/i }),
    );
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await user.click(screen.getByTestId('route-path'));
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('delete shows confirm dialog before firing DELETE', async () => {
    let deleteCalled = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      const method = (init?.method ?? 'GET').toUpperCase();
      if (url.endsWith('/sessions') && method === 'GET') {
        return jsonResponse([makeSession(9, 'To be deleted')]);
      }
      if (url.endsWith('/sessions/9') && method === 'DELETE') {
        deleteCalled = true;
        return new Response(null, { status: 204 });
      }
      return new Response(null, { status: 404 });
    });

    const user = userEvent.setup();
    renderSidebar();

    await screen.findByRole('button', { name: 'To be deleted' });
    await user.click(
      screen.getByRole('button', { name: /actions for to be deleted/i }),
    );
    await user.click(screen.getByRole('menuitem', { name: /delete/i }));

    const dialog = await screen.findByRole('dialog', {
      name: /confirm delete/i,
    });
    expect(dialog).toBeInTheDocument();
    expect(deleteCalled).toBe(false);

    // Cancel closes the dialog without deleting.
    await user.click(within(dialog).getByRole('button', { name: /cancel/i }));
    expect(
      screen.queryByRole('dialog', { name: /confirm delete/i }),
    ).not.toBeInTheDocument();
    expect(deleteCalled).toBe(false);

    // Re-open and confirm actually deletes.
    await user.click(
      screen.getByRole('button', { name: /actions for to be deleted/i }),
    );
    await user.click(screen.getByRole('menuitem', { name: /delete/i }));
    const dialog2 = await screen.findByRole('dialog', {
      name: /confirm delete/i,
    });
    await user.click(
      within(dialog2).getByRole('button', { name: /^delete$/i }),
    );

    await waitFor(() => expect(deleteCalled).toBe(true));
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'To be deleted' }),
      ).not.toBeInTheDocument(),
    );
  });
});
