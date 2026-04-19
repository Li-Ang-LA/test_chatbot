import { Outlet, useParams } from 'react-router-dom';
import { Sidebar } from '../sidebar/Sidebar';
import { ChatView } from '../chat/ChatView';
import { useChatStream } from '../chat/useChatStream';

export function AppShell() {
  return (
    <div className="flex min-h-screen bg-white">
      <Sidebar />
      <main className="flex min-h-screen flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  );
}

export function EmptyHomePlaceholder() {
  return (
    <div
      data-state="no-session"
      className="flex flex-1 items-center justify-center text-neutral-500"
    >
      <p>Select a chat from the sidebar, or start a new one.</p>
    </div>
  );
}

export function ChatSessionPlaceholder() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const numericId = sessionId ? Number(sessionId) : undefined;
  const { messages, error, send } = useChatStream(numericId);

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
