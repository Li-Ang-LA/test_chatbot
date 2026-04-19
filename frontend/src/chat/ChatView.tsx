import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { SUGGESTIONS } from './suggestions';
import { AssistantMarkdown } from './AssistantMarkdown';
import type { ChatMessage } from './types';

type Props = {
  messages: ChatMessage[];
  onSubmit?: (content: string) => void;
};

export function ChatView({ messages, onSubmit }: Props) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const isEmpty = messages.length === 0;

  const contentSignature = messages
    .map((m) => `${m.id}:${m.content.length}`)
    .join('|');

  useEffect(() => {
    if (isEmpty) return;
    bottomRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [contentSignature, isEmpty]);

  function fillAndFocus(suggestion: string) {
    setValue(suggestion);
    inputRef.current?.focus();
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || !onSubmit) return;
    onSubmit(trimmed);
    setValue('');
  }

  return (
    <section
      data-state={isEmpty ? 'empty' : 'active'}
      aria-label={isEmpty ? 'Start a new chat' : 'Chat conversation'}
      className={`flex flex-1 flex-col transition-all duration-300 ${
        isEmpty ? 'justify-center' : ''
      }`}
    >
      {!isEmpty && (
        <div
          className="flex-1 overflow-y-auto px-6 py-8"
          aria-live="polite"
          aria-label="Messages"
        >
          <ol className="mx-auto flex max-w-3xl flex-col gap-6">
            {messages.map((m) => (
              <li
                key={m.id}
                data-role={m.role}
                className={
                  m.role === 'user'
                    ? 'max-w-[80%] self-end rounded-2xl bg-neutral-900 px-4 py-2 text-sm text-white'
                    : 'w-full text-base leading-relaxed text-neutral-800'
                }
              >
                {m.role === 'assistant' ? (
                  <AssistantMarkdown content={m.content} />
                ) : (
                  m.content
                )}
              </li>
            ))}
          </ol>
          <div ref={bottomRef} data-testid="chat-bottom" />
        </div>
      )}

      <div
        className={
          isEmpty ? 'p-6' : 'border-t border-neutral-200 bg-white px-4 py-3'
        }
      >
        <div className="mx-auto w-full max-w-2xl space-y-4">
          {isEmpty && (
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
          )}

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
      </div>
    </section>
  );
}
