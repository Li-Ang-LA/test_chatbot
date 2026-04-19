import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import {
  AppShell,
  ChatSessionPlaceholder,
  EmptyHomePlaceholder,
} from './AppShell';
import { AuthProvider } from '../auth/AuthContext';
import { RequireAuth } from '../auth/RequireAuth';

function RoutePath() {
  const { pathname } = useLocation();
  return <div data-testid="route-path">{pathname}</div>;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function renderApp(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <RoutePath />
        <Routes>
          <Route path="/login" element={<div>Login Screen</div>} />
          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route path="/" element={<EmptyHomePlaceholder />} />
            <Route path="/c/:sessionId" element={<ChatSessionPlaceholder />} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const alice = {
  id: 1,
  email: 'alice@example.com',
  username: 'alice',
  created_at: '2026-01-01T00:00:00Z',
};

const sessionRow = {
  id: 11,
  title: 'First chat',
  claude_session_id: null,
  system_prompt: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('AppShell', () => {
  it('clicking a session row updates URL to /c/:id', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      const method = (init?.method ?? 'GET').toUpperCase();
      if (url.endsWith('/auth/me') && method === 'GET')
        return jsonResponse(alice);
      if (url.endsWith('/sessions') && method === 'GET')
        return jsonResponse([sessionRow]);
      return new Response(null, { status: 404 });
    });

    const user = userEvent.setup();
    renderApp();

    // Empty-state placeholder visible until we pick a chat.
    expect(
      await screen.findByText(/select a chat from the sidebar/i),
    ).toBeInTheDocument();

    const row = await screen.findByRole('button', { name: 'First chat' });
    await user.click(row);

    await waitFor(() =>
      expect(screen.getByTestId('route-path')).toHaveTextContent('/c/11'),
    );
    expect(screen.getByText(/^Session 11$/)).toBeInTheDocument();
  });

  it('logout clears auth and redirects to /login', async () => {
    const logoutCalls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      const method = (init?.method ?? 'GET').toUpperCase();
      if (url.endsWith('/auth/me') && method === 'GET')
        return jsonResponse(alice);
      if (url.endsWith('/sessions') && method === 'GET')
        return jsonResponse([]);
      if (url.endsWith('/auth/logout') && method === 'POST') {
        logoutCalls.push(url);
        return new Response(null, { status: 204 });
      }
      return new Response(null, { status: 404 });
    });

    const user = userEvent.setup();
    renderApp();

    // Wait until the shell is mounted (user menu rendered).
    const logoutBtn = await screen.findByRole('button', { name: /log out/i });
    await user.click(logoutBtn);

    await waitFor(() =>
      expect(screen.getByText(/login screen/i)).toBeInTheDocument(),
    );
    expect(logoutCalls).toHaveLength(1);
    expect(screen.getByTestId('route-path')).toHaveTextContent('/login');
  });
});
