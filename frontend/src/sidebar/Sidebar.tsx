import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
} from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  LogOut,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  SquarePen,
} from 'lucide-react';
import {
  createSession,
  deleteSession,
  listSessions,
  updateSession,
} from '../sessions/api';
import type { ChatSession } from '../sessions/api';
import { useAuth } from '../auth/useAuth';

const COLLAPSED_KEY = 'sidebar:collapsed';

function readCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(COLLAPSED_KEY) === '1';
}

export function Sidebar() {
  const navigate = useNavigate();
  const { sessionId: activeIdParam } = useParams();
  const activeId = activeIdParam ? Number(activeIdParam) : null;

  const [collapsed, setCollapsed] = useState<boolean>(() => readCollapsed());
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [menuOpenFor, setMenuOpenFor] = useState<number | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(
    null,
  );

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch(() => {
        // Silently ignore for now; global error handling lands in M6.
      });
  }, []);

  useEffect(() => {
    window.localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  // Close the row "..." menu on click-outside or Escape.
  useEffect(() => {
    if (menuOpenFor === null) return;

    function handleMouseDown(e: MouseEvent) {
      const target = e.target as Node | null;
      if (!target) return;
      const openMenu = document.querySelector('[data-row-menu="true"]');
      const triggers = document.querySelectorAll(
        '[aria-haspopup="menu"][data-row-menu-trigger="true"]',
      );
      const insideMenu = openMenu?.contains(target) ?? false;
      const onTrigger = Array.from(triggers).some((t) => t.contains(target));
      if (!insideMenu && !onTrigger) setMenuOpenFor(null);
    }
    function handleKey(e: globalThis.KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpenFor(null);
    }
    document.addEventListener('mousedown', handleMouseDown);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleMouseDown);
      document.removeEventListener('keydown', handleKey);
    };
  }, [menuOpenFor]);

  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), []);

  const handleNew = useCallback(async () => {
    try {
      const created = await createSession();
      setSessions((prev) => [created, ...prev]);
      navigate(`/c/${created.id}`);
    } catch (err) {
      console.error('Failed to create session', err);
    }
  }, [navigate]);

  const handleRename = useCallback(async (id: number, nextTitle: string) => {
    const trimmed = nextTitle.trim();
    if (!trimmed) {
      setRenamingId(null);
      return;
    }
    try {
      const updated = await updateSession(id, { title: trimmed });
      setSessions((prev) => prev.map((s) => (s.id === id ? updated : s)));
    } catch (err) {
      console.error('Failed to rename session', err);
    } finally {
      setRenamingId(null);
    }
  }, []);

  const handleConfirmDelete = useCallback(
    async (id: number) => {
      try {
        await deleteSession(id);
        setSessions((prev) => prev.filter((s) => s.id !== id));
        if (activeId === id) navigate('/');
      } catch (err) {
        console.error('Failed to delete session', err);
      } finally {
        setConfirmingDeleteId(null);
      }
    },
    [activeId, navigate],
  );

  if (collapsed) {
    return (
      <aside
        aria-label="Sidebar"
        data-collapsed="true"
        className="flex h-screen w-14 flex-col items-center gap-2 border-r border-neutral-200 bg-neutral-50 py-3"
      >
        <button
          type="button"
          aria-label="Expand sidebar"
          onClick={toggleCollapsed}
          className="rounded-xl p-2 hover:bg-neutral-200"
        >
          <PanelLeftOpen size={18} aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="New session"
          onClick={() => void handleNew()}
          className="rounded-xl p-2 hover:bg-neutral-200"
        >
          <SquarePen size={18} aria-hidden="true" />
        </button>
        <UserMenu collapsed />
      </aside>
    );
  }

  return (
    <aside
      aria-label="Sidebar"
      data-collapsed="false"
      className="flex h-screen w-64 flex-col border-r border-neutral-200 bg-neutral-50"
    >
      <div className="flex items-center justify-between gap-2 px-3 py-3">
        <button
          type="button"
          aria-label="Collapse sidebar"
          onClick={toggleCollapsed}
          className="rounded-xl p-2 hover:bg-neutral-200"
        >
          <PanelLeftClose size={18} aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="New session"
          onClick={() => void handleNew()}
          className="rounded-xl p-2 hover:bg-neutral-200"
        >
          <SquarePen size={18} aria-hidden="true" />
        </button>
      </div>

      <ul className="flex-1 overflow-y-auto px-2 pb-3" role="list">
        {sessions.map((session) => (
          <SessionRow
            key={session.id}
            session={session}
            isActive={session.id === activeId}
            isRenaming={renamingId === session.id}
            isMenuOpen={menuOpenFor === session.id}
            onOpen={() => navigate(`/c/${session.id}`)}
            onOpenMenu={() =>
              setMenuOpenFor((cur) => (cur === session.id ? null : session.id))
            }
            onCloseMenu={() => setMenuOpenFor(null)}
            onStartRename={() => {
              setMenuOpenFor(null);
              setRenamingId(session.id);
            }}
            onFinishRename={(title) => void handleRename(session.id, title)}
            onCancelRename={() => setRenamingId(null)}
            onRequestDelete={() => {
              setMenuOpenFor(null);
              setConfirmingDeleteId(session.id);
            }}
          />
        ))}
      </ul>

      <UserMenu />

      {confirmingDeleteId !== null && (
        <DeleteConfirmDialog
          title={
            sessions.find((s) => s.id === confirmingDeleteId)?.title ??
            'this chat'
          }
          onConfirm={() => void handleConfirmDelete(confirmingDeleteId)}
          onCancel={() => setConfirmingDeleteId(null)}
        />
      )}
    </aside>
  );
}

function UserMenu({ collapsed = false }: { collapsed?: boolean }) {
  const { user, logout } = useAuth();
  if (!user) return null;
  const initial = user.username.slice(0, 1).toUpperCase();

  if (collapsed) {
    return (
      <div className="mt-auto flex flex-col items-center gap-2">
        <div
          aria-label={`Signed in as ${user.username}`}
          className="flex size-8 items-center justify-center rounded-full bg-neutral-300 text-sm font-medium text-neutral-800"
        >
          {initial}
        </div>
        <button
          type="button"
          aria-label="Log out"
          onClick={() => void logout()}
          className="rounded-xl p-2 hover:bg-neutral-200"
        >
          <LogOut size={16} aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 border-t border-neutral-200 px-3 py-3">
      <div
        aria-hidden="true"
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-neutral-300 text-sm font-medium text-neutral-800"
      >
        {initial}
      </div>
      <div className="min-w-0 flex-1 truncate text-sm text-neutral-700">
        {user.username}
      </div>
      <button
        type="button"
        aria-label="Log out"
        onClick={() => void logout()}
        className="rounded-xl p-2 hover:bg-neutral-200"
      >
        <LogOut size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

type SessionRowProps = {
  session: ChatSession;
  isActive: boolean;
  isRenaming: boolean;
  isMenuOpen: boolean;
  onOpen: () => void;
  onOpenMenu: () => void;
  onCloseMenu: () => void;
  onStartRename: () => void;
  onFinishRename: (title: string) => void;
  onCancelRename: () => void;
  onRequestDelete: () => void;
};

function SessionRow({
  session,
  isActive,
  isRenaming,
  isMenuOpen,
  onOpen,
  onOpenMenu,
  onCloseMenu,
  onStartRename,
  onFinishRename,
  onCancelRename,
  onRequestDelete,
}: SessionRowProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  // Set by Enter/Escape in the rename input so the subsequent blur event
  // doesn't fire a duplicate submit.
  const renameHandledRef = useRef(false);

  useEffect(() => {
    if (isRenaming) inputRef.current?.focus();
  }, [isRenaming]);

  // When the row's action menu opens, focus the first menuitem so keyboard
  // users can navigate with Arrow/Home/End/Escape immediately.
  useEffect(() => {
    if (!isMenuOpen) return;
    const first =
      menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]');
    first?.focus();
  }, [isMenuOpen]);

  function handleRenameKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      renameHandledRef.current = true;
      onFinishRename(e.currentTarget.value);
    } else if (e.key === 'Escape') {
      renameHandledRef.current = true;
      onCancelRename();
    }
  }

  function handleRenameBlur(e: FocusEvent<HTMLInputElement>) {
    if (renameHandledRef.current) {
      renameHandledRef.current = false;
      return;
    }
    onFinishRename(e.currentTarget.value);
  }

  function handleMenuKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const items = menuRef.current
      ? Array.from(
          menuRef.current.querySelectorAll<HTMLButtonElement>(
            '[role="menuitem"]',
          ),
        )
      : [];
    if (items.length === 0) return;
    const activeIdx = items.findIndex((el) => el === document.activeElement);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      items[(activeIdx + 1 + items.length) % items.length].focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      items[(activeIdx - 1 + items.length) % items.length].focus();
    } else if (e.key === 'Home') {
      e.preventDefault();
      items[0].focus();
    } else if (e.key === 'End') {
      e.preventDefault();
      items[items.length - 1].focus();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onCloseMenu();
      triggerRef.current?.focus();
    }
  }

  const base =
    'group relative flex items-center justify-between rounded-xl px-3 py-2 text-sm';
  const activeCls = isActive
    ? 'bg-neutral-200 text-neutral-900'
    : 'text-neutral-700 hover:bg-neutral-200';

  return (
    <li className={`${base} ${activeCls}`} data-active={isActive || undefined}>
      {isRenaming ? (
        <input
          ref={inputRef}
          defaultValue={session.title}
          aria-label="Rename session"
          onKeyDown={handleRenameKey}
          onBlur={handleRenameBlur}
          className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm outline-none focus:border-neutral-900"
        />
      ) : (
        <button
          type="button"
          onClick={onOpen}
          className="min-w-0 flex-1 truncate text-left"
        >
          {session.title}
        </button>
      )}

      {!isRenaming && (
        <div className="relative ml-2 flex-shrink-0">
          <button
            ref={triggerRef}
            type="button"
            aria-label={`Actions for ${session.title}`}
            aria-haspopup="menu"
            aria-expanded={isMenuOpen}
            data-row-menu-trigger="true"
            onClick={onOpenMenu}
            className="rounded-md p-1 opacity-0 group-hover:opacity-100 hover:bg-neutral-300 data-[open=true]:opacity-100"
            data-open={isMenuOpen || undefined}
          >
            <MoreHorizontal size={16} aria-hidden="true" />
          </button>
          {isMenuOpen && (
            <div
              ref={menuRef}
              role="menu"
              data-row-menu="true"
              onKeyDown={handleMenuKeyDown}
              className="absolute top-full right-0 z-10 mt-1 w-32 rounded-xl border border-neutral-200 bg-white py-1 shadow-sm"
            >
              <button
                type="button"
                role="menuitem"
                onClick={onStartRename}
                className="block w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-neutral-100"
              >
                Rename
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={onRequestDelete}
                className="block w-full rounded-md px-3 py-1.5 text-left text-sm text-red-600 hover:bg-neutral-100"
              >
                Delete
              </button>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

type DeleteConfirmDialogProps = {
  title: string;
  onConfirm: () => void;
  onCancel: () => void;
};

function DeleteConfirmDialog({
  title,
  onConfirm,
  onCancel,
}: DeleteConfirmDialogProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirm delete"
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4"
    >
      <div className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-6 shadow-lg">
        <h2 className="text-lg font-semibold text-neutral-900">Delete chat?</h2>
        <p className="text-sm text-neutral-700">
          This will permanently remove &ldquo;{title}&rdquo; and its messages.
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-xl px-4 py-2 text-sm text-neutral-700 hover:bg-neutral-100"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-xl bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
