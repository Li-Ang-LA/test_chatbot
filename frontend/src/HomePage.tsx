import { useAuth } from './auth/useAuth';

export function HomePage() {
  const { user, logout } = useAuth();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-neutral-50 p-4">
      <h1 className="text-3xl font-semibold text-neutral-900">
        Hello, {user?.username}
      </h1>
      <button
        type="button"
        onClick={() => void logout()}
        className="rounded-xl bg-neutral-900 px-4 py-2 font-medium text-white hover:bg-neutral-800"
      >
        Log out
      </button>
    </main>
  );
}
