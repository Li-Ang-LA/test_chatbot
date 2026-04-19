import { Outlet, useParams } from 'react-router-dom';
import { Sidebar } from '../sidebar/Sidebar';
import { SessionChat } from '../chat/SessionChat';

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
  const numericId = Number(sessionId);
  if (!Number.isFinite(numericId)) return null;
  // `key` forces SessionChat (and its useChatStream state + in-flight fetch)
  // to remount on navigation between sessions, so nothing leaks across routes.
  return <SessionChat key={numericId} sessionId={numericId} />;
}
