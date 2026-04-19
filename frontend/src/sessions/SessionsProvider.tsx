import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { listSessions } from './api';
import type { ChatSession } from './api';
import {
  DEFAULT_SESSION_TITLE,
  SessionsContext,
  deriveAutoTitle,
  sortSessionsByActivity,
} from './sessionsContext';

export function SessionsProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  useEffect(() => {
    let cancelled = false;
    listSessions().then(
      (fresh) => {
        if (!cancelled) setSessions(fresh);
      },
      () => {
        // Global error surface lands in M6.
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const refetch = useCallback(async () => {
    try {
      const fresh = await listSessions();
      setSessions(fresh);
    } catch {
      // Global error surface lands in M6.
    }
  }, []);

  const bumpSessionForSend = useCallback(
    (sessionId: number, content: string) => {
      const now = new Date().toISOString();
      const derived = deriveAutoTitle(content);
      setSessions((prev) =>
        sortSessionsByActivity(
          prev.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  title:
                    s.title === DEFAULT_SESSION_TITLE && derived
                      ? derived
                      : s.title,
                  updated_at: now,
                }
              : s,
          ),
        ),
      );
    },
    [],
  );

  return (
    <SessionsContext.Provider
      value={{ sessions, setSessions, refetch, bumpSessionForSend }}
    >
      {children}
    </SessionsContext.Provider>
  );
}
