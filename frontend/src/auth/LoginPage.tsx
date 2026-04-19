import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from './useAuth';
import { validateEmail } from './validation';

type Errors = { email?: string; password?: string; form?: string };

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  const redirectTo =
    (location.state as { from?: { pathname?: string } } | null)?.from
      ?.pathname ?? '/';

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const next: Errors = {
      email: validateEmail(email) ?? undefined,
      password: password ? undefined : 'Password is required',
    };
    setErrors(next);
    if (next.email || next.password) return;

    setSubmitting(true);
    try {
      await login(email, password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      const message =
        (err as { message?: string })?.message ??
        'Login failed. Please try again.';
      setErrors({ form: message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-50 p-4">
      <form
        onSubmit={handleSubmit}
        noValidate
        aria-label="Log in"
        className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-8 shadow-sm"
      >
        <h1 className="text-2xl font-semibold text-neutral-900">Log in</h1>

        {errors.form && (
          <div
            role="alert"
            className="rounded-xl bg-red-50 p-3 text-sm text-red-700"
          >
            {errors.form}
          </div>
        )}

        <div className="space-y-1">
          <label
            htmlFor="email"
            className="text-sm font-medium text-neutral-700"
          >
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={errors.email ? 'email-error' : undefined}
            className="w-full rounded-xl border border-neutral-300 px-3 py-2 outline-none focus:border-neutral-900"
          />
          {errors.email && (
            <p id="email-error" className="text-sm text-red-600">
              {errors.email}
            </p>
          )}
        </div>

        <div className="space-y-1">
          <label
            htmlFor="password"
            className="text-sm font-medium text-neutral-700"
          >
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={errors.password ? 'password-error' : undefined}
            className="w-full rounded-xl border border-neutral-300 px-3 py-2 outline-none focus:border-neutral-900"
          />
          {errors.password && (
            <p id="password-error" className="text-sm text-red-600">
              {errors.password}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-xl bg-neutral-900 px-4 py-2 font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
        >
          {submitting ? 'Signing in…' : 'Log in'}
        </button>

        <p className="text-center text-sm text-neutral-600">
          Don&apos;t have an account?{' '}
          <Link to="/signup" className="font-medium text-neutral-900 underline">
            Sign up
          </Link>
        </p>
      </form>
    </main>
  );
}
