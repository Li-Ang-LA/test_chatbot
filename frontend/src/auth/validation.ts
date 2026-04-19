const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const USERNAME_RE = /^[A-Za-z0-9_.-]+$/;

export function validateEmail(email: string): string | null {
  if (!email) return 'Email is required';
  if (!EMAIL_RE.test(email)) return 'Enter a valid email address';
  return null;
}

export function validatePassword(password: string): string | null {
  if (!password) return 'Password is required';
  if (password.length < 8) return 'Password must be at least 8 characters';
  return null;
}

export function validateUsername(username: string): string | null {
  if (!username) return 'Username is required';
  if (username.length < 3) return 'Username must be at least 3 characters';
  if (!USERNAME_RE.test(username))
    return 'Username may only contain letters, numbers, dot, dash, underscore';
  return null;
}
