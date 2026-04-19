import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './AuthContext';
import { RequireAuth } from './RequireAuth';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route
            path="/"
            element={
              <RequireAuth>
                <div>Protected Home</div>
              </RequireAuth>
            }
          />
          <Route path="/login" element={<div>Login Screen</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('RequireAuth', () => {
  it('redirects to /login when unauthenticated', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Not authenticated' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    renderAt('/');
    expect(await screen.findByText(/login screen/i)).toBeInTheDocument();
    expect(screen.queryByText(/protected home/i)).not.toBeInTheDocument();
  });

  it('renders children when authenticated', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 1,
          email: 'a@b.co',
          username: 'alice',
          created_at: '2026-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    renderAt('/');
    expect(await screen.findByText(/protected home/i)).toBeInTheDocument();
  });
});
