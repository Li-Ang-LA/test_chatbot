import { useCallback } from 'react';
import { ChatView } from './ChatView';
import { useChatStream } from './useChatStream';
import { useSessions } from '../sessions/sessionsContext';

export function SessionChat({ sessionId }: { sessionId: number }) {
  const { messages, error, send } = useChatStream(sessionId);
  const { bumpSessionForSend, refetch } = useSessions();

  const handleSend = useCallback(
    async (content: string) => {
      // Optimistically retitle a "New chat" and float it to the top of the
      // sidebar list before the round-trip; reconcile with the server's
      // canonical title/updated_at after the stream resolves.
      bumpSessionForSend(sessionId, content);
      await send(content);
      void refetch();
    },
    [bumpSessionForSend, refetch, send, sessionId],
  );

  return (
    <>
      {error && (
        <div
          role="alert"
          className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700"
        >
          {error}
        </div>
      )}
      <ChatView messages={messages} onSubmit={handleSend} />
    </>
  );
}
