import { Outlet } from 'react-router-dom';
import { Sidebar } from '../sidebar/Sidebar';
import { EmptyChatView } from '../chat/EmptyChatView';

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
  // M3.4 (issue #13) will introduce the active-chat layout and the
  // empty-to-active transition driven by message state. Until then, freshly
  // opened sessions render the centered empty-state hero.
  return <EmptyChatView />;
}
