const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export type ChatSession = {
  id: number;
  title: string;
  claude_session_id: string | null;
  system_prompt: string | null;
  created_at: string;
  updated_at: string;
};

export type ApiError = { status: number; message: string };

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
    ...init,
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      if (typeof data?.detail === 'string') message = data.detail;
    } catch {
      // ignore body parse errors
    }
    const err: ApiError = { status: res.status, message };
    throw err;
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function listSessions(): Promise<ChatSession[]> {
  return request<ChatSession[]>('/sessions');
}

export function createSession(
  input: { title?: string; system_prompt?: string } = {},
): Promise<ChatSession> {
  return request<ChatSession>('/sessions', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function updateSession(
  id: number,
  input: { title?: string; system_prompt?: string | null },
): Promise<ChatSession> {
  return request<ChatSession>(`/sessions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  });
}

export function deleteSession(id: number): Promise<void> {
  return request<void>(`/sessions/${id}`, { method: 'DELETE' });
}
