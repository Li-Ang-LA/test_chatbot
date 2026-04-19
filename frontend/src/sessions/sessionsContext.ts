import {
  createContext,
  useContext,
  type Dispatch,
  type SetStateAction,
} from 'react';
import type { ChatSession } from './api';

export const DEFAULT_SESSION_TITLE = 'New chat';
export const MAX_AUTO_TITLE_LEN = 60;

export type SessionsContextValue = {
  sessions: ChatSession[];
  setSessions: Dispatch<SetStateAction<ChatSession[]>>;
  refetch: () => Promise<void>;
  /**
   * Bump a session's title (if still default) and `updated_at` locally, then
   * re-sort. Used by SessionChat to drive instant sidebar updates when a user
   * sends a message; the backend's canonical state is reconciled by `refetch`.
   */
  bumpSessionForSend: (sessionId: number, content: string) => void;
};

export const SessionsContext = createContext<SessionsContextValue | null>(null);

export function useSessions(): SessionsContextValue {
  const ctx = useContext(SessionsContext);
  if (!ctx) {
    throw new Error('useSessions must be used inside <SessionsProvider>');
  }
  return ctx;
}

export function deriveAutoTitle(content: string): string {
  return content.trim().slice(0, MAX_AUTO_TITLE_LEN);
}

export function sortSessionsByActivity(list: ChatSession[]): ChatSession[] {
  // Mirrors the backend ordering: updated_at desc, then id desc as tiebreaker.
  return [...list].sort((a, b) => {
    const cmp = b.updated_at.localeCompare(a.updated_at);
    return cmp !== 0 ? cmp : b.id - a.id;
  });
}
