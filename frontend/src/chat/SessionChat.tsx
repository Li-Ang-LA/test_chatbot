import { ChatView } from './ChatView';
import { useChatStream } from './useChatStream';

export function SessionChat({ sessionId }: { sessionId: number }) {
  const { messages, error, send } = useChatStream(sessionId);

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
      <ChatView messages={messages} onSubmit={send} />
    </>
  );
}
