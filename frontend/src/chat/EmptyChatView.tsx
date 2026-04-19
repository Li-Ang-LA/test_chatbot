import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { SUGGESTIONS } from './suggestions';

type Props = {
  onSubmit?: (content: string) => void;
};

export function EmptyChatView({ onSubmit }: Props) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  function fillAndFocus(suggestion: string) {
    setValue(suggestion);
    inputRef.current?.focus();
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || !onSubmit) return;
    onSubmit(trimmed);
  }

  return (
    <section
      data-state="empty"
      className="flex flex-1 items-center justify-center p-6"
      aria-label="Start a new chat"
    >
      <div className="w-full max-w-2xl space-y-4">
        <ul
          className="grid grid-cols-1 gap-2 sm:grid-cols-2"
          aria-label="Suggested prompts"
        >
          {SUGGESTIONS.map((s) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => fillAndFocus(s)}
                className="w-full rounded-2xl border border-neutral-200 bg-white px-4 py-3 text-left text-sm text-neutral-700 shadow-sm hover:bg-neutral-50"
              >
                {s}
              </button>
            </li>
          ))}
        </ul>

        <form
          onSubmit={handleSubmit}
          className="flex items-end gap-2 rounded-2xl border border-neutral-300 bg-white p-2 shadow-sm focus-within:border-neutral-900"
        >
          <textarea
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-label="Message"
            placeholder="Ask anything…"
            rows={1}
            className="min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none"
          />
          <button
            type="submit"
            disabled={!value.trim()}
            className="rounded-xl bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </section>
  );
}
