import { useState } from 'react';
import { Outlet, useParams } from 'react-router-dom';
import { Sidebar } from '../sidebar/Sidebar';
import { ChatView } from '../chat/ChatView';
import type { ChatMessage } from '../chat/types';

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
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  function handleSubmit(content: string) {
    setMessages((prev) => [
      ...prev,
      { id: `${sessionId ?? 'local'}-${prev.length}`, role: 'user', content },
    ]);
  }

  return <ChatView messages={messages} onSubmit={handleSubmit} />;
}
