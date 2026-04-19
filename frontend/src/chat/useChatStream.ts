import { useCallback, useEffect, useRef, useState } from 'react';
import { API_URL, getSession } from '../sessions/api';
import type { PersistedMessage } from '../sessions/api';
import type { ChatMessage } from './types';

type HookState = {
  messages: ChatMessage[];
  streaming: string | null;
  error: string | null;
  isLoading: boolean;
  isSending: boolean;
};

type SSEHandlers = {
  onDelta: (text: string) => void;
  onDone: (text: string) => void;
  onError: (message: string) => void;
};

function toChatMessage(m: PersistedMessage): ChatMessage {
  return { id: m.id, role: m.role, content: m.content };
}

function parseBlock(
  block: string,
): { event: string; data: Record<string, unknown> } | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice('event:'.length).trim();
    else if (line.startsWith('data:'))
      dataLines.push(line.slice('data:'.length).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) };
  } catch {
    return null;
  }
}

async function consumeSSE(
  body: ReadableStream<Uint8Array>,
  handlers: SSEHandlers,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });

      let sep = buffer.indexOf('\n\n');
      while (sep !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const parsed = parseBlock(block);
        if (parsed) {
          const { event, data } = parsed;
          if (event === 'delta' && typeof data.text === 'string') {
            handlers.onDelta(data.text);
          } else if (event === 'done' && typeof data.text === 'string') {
            handlers.onDone(data.text);
            return;
          } else if (event === 'error') {
            const msg =
              typeof data.error === 'string' ? data.error : 'stream error';
            handlers.onError(msg);
            return;
          }
        }
        sep = buffer.indexOf('\n\n');
      }
    }
  } finally {
    reader.releaseLock();
  }
}

const EMPTY_STATE: HookState = {
  messages: [],
  streaming: null,
  error: null,
  isLoading: false,
  isSending: false,
};

function initialState(sessionId: number | undefined): HookState {
  return sessionId == null ? EMPTY_STATE : { ...EMPTY_STATE, isLoading: true };
}

export function useChatStream(sessionId: number | undefined) {
  const [state, setState] = useState<HookState>(() => initialState(sessionId));
  const [trackedSessionId, setTrackedSessionId] = useState(sessionId);

  if (sessionId !== trackedSessionId) {
    setTrackedSessionId(sessionId);
    setState(initialState(sessionId));
  }

  const abortRef = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);

  useEffect(() => {
    if (sessionId == null) return;

    let cancelled = false;

    getSession(sessionId)
      .then((detail) => {
        if (cancelled) return;
        setState((prev) => ({
          ...prev,
          messages: detail.messages.map(toChatMessage),
          isLoading: false,
        }));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err && typeof err === 'object' && 'message' in err
            ? String((err as { message: unknown }).message)
            : 'Failed to load session';
        setState((prev) => ({ ...prev, error: message, isLoading: false }));
      });

    return () => {
      cancelled = true;
      abortRef.current?.abort();
      abortRef.current = null;
      sendingRef.current = false;
    };
  }, [sessionId]);

  const send = useCallback(
    async (content: string) => {
      if (sessionId == null) return;
      if (sendingRef.current) return;
      sendingRef.current = true;

      const userMessage: ChatMessage = {
        id: `local-user-${Date.now()}`,
        role: 'user',
        content,
      };
      setState((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
        streaming: '',
        error: null,
        isSending: true,
      }));

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        const res = await fetch(`${API_URL}/sessions/${sessionId}/messages`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content }),
          signal: ctrl.signal,
        });

        if (!res.ok || !res.body) {
          setState((prev) => ({
            ...prev,
            streaming: null,
            error: `Request failed (${res.status})`,
            isSending: false,
          }));
          return;
        }

        await consumeSSE(res.body, {
          onDelta: (text) => {
            setState((prev) => ({
              ...prev,
              streaming: (prev.streaming ?? '') + text,
            }));
          },
          onDone: (text) => {
            setState((prev) => ({
              ...prev,
              messages: [
                ...prev.messages,
                {
                  id: `local-assistant-${Date.now()}`,
                  role: 'assistant',
                  content: text,
                },
              ],
              streaming: null,
              isSending: false,
            }));
          },
          onError: (message) => {
            setState((prev) => ({
              ...prev,
              streaming: null,
              error: message,
              isSending: false,
            }));
          },
        });
      } catch (err: unknown) {
        if (err && typeof err === 'object' && 'name' in err) {
          const name = (err as { name: unknown }).name;
          if (name === 'AbortError') {
            setState((prev) => ({
              ...prev,
              streaming: null,
              isSending: false,
            }));
            return;
          }
        }
        const message =
          err && typeof err === 'object' && 'message' in err
            ? String((err as { message: unknown }).message)
            : 'Stream failed';
        setState((prev) => ({
          ...prev,
          streaming: null,
          error: message,
          isSending: false,
        }));
      } finally {
        sendingRef.current = false;
        if (abortRef.current === ctrl) abortRef.current = null;
      }
    },
    [sessionId],
  );

  const visibleMessages: ChatMessage[] =
    state.streaming != null
      ? [
          ...state.messages,
          {
            id: 'streaming',
            role: 'assistant',
            content: state.streaming,
          },
        ]
      : state.messages;

  return {
    messages: visibleMessages,
    error: state.error,
    isLoading: state.isLoading,
    isSending: state.isSending,
    send,
  };
}
