import { Outlet, useParams } from 'react-router-dom';
import { Sidebar } from '../sidebar/Sidebar';

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
  const { sessionId } = useParams();
  return (
    <div
      data-state="session-selected"
      data-session-id={sessionId}
      className="flex flex-1 items-center justify-center text-neutral-500"
    >
      <p>Session {sessionId}</p>
    </div>
  );
}
