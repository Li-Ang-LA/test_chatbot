import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { ChatView } from './ChatView';
import { SUGGESTIONS } from './suggestions';
import type { ChatMessage } from './types';

afterEach(() => {
  cleanup();
});

function Harness() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  return (
    <ChatView
      messages={messages}
      onSubmit={(content) =>
        setMessages((prev) => [
          ...prev,
          { id: prev.length, role: 'user', content },
        ])
      }
    />
  );
}

describe('ChatView empty state (M3.3)', () => {
  it('marks the container with data-state="empty" when no messages', () => {
    render(<ChatView messages={[]} />);
    const container = screen.getByRole('region', { name: /start a new chat/i });
    expect(container).toHaveAttribute('data-state', 'empty');
  });

  it('renders all four suggestion bubbles', () => {
    render(<ChatView messages={[]} />);
    for (const s of SUGGESTIONS) {
      expect(screen.getByRole('button', { name: s })).toBeInTheDocument();
    }
    expect(SUGGESTIONS).toHaveLength(4);
  });

  it('clicking a suggestion bubble populates the input', async () => {
    const user = userEvent.setup();
    render(<ChatView messages={[]} />);

    const input = screen.getByRole('textbox', { name: /message/i });
    expect(input).toHaveValue('');

    await user.click(
      screen.getByRole('button', { name: /explain quicksort/i }),
    );
    expect(input).toHaveValue('Explain quicksort');
  });

  it('submits the trimmed value via onSubmit', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<ChatView messages={[]} onSubmit={onSubmit} />);

    const input = screen.getByRole('textbox', { name: /message/i });
    await user.type(input, '   hi there   ');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith('hi there');
  });

  it('disables Send when input is empty or whitespace', async () => {
    const user = userEvent.setup();
    render(<ChatView messages={[]} />);
    const send = screen.getByRole('button', { name: /^send$/i });
    expect(send).toBeDisabled();

    await user.type(screen.getByRole('textbox', { name: /message/i }), '   ');
    expect(send).toBeDisabled();
  });
});

describe('ChatView active state (M3.4)', () => {
  it('flips data-state from empty to active after the first message', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(
      screen.getByRole('region', { name: /start a new chat/i }),
    ).toHaveAttribute('data-state', 'empty');

    await user.type(
      screen.getByRole('textbox', { name: /message/i }),
      'hello there',
    );
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    const activeContainer = screen.getByRole('region', {
      name: /chat conversation/i,
    });
    expect(activeContainer).toHaveAttribute('data-state', 'active');
    expect(
      screen.queryByRole('region', { name: /start a new chat/i }),
    ).not.toBeInTheDocument();
  });

  it('renders user messages with data-role="user" and assistant with data-role="assistant"', () => {
    const messages: ChatMessage[] = [
      { id: 1, role: 'user', content: 'what is quicksort?' },
      { id: 2, role: 'assistant', content: 'A divide-and-conquer sort…' },
    ];
    render(<ChatView messages={messages} />);

    const userNode = screen.getByText('what is quicksort?').closest('li');
    expect(userNode).toHaveAttribute('data-role', 'user');
    expect(userNode!.className).toMatch(/bg-neutral-900/);

    const assistantNode = screen
      .getByText('A divide-and-conquer sort…')
      .closest('li');
    expect(assistantNode).toHaveAttribute('data-role', 'assistant');
    expect(assistantNode!.className).not.toMatch(/bg-neutral-900/);
  });

  it('auto-scrolls to the bottom when streaming new content', () => {
    const scrollSpy = vi
      .spyOn(HTMLElement.prototype, 'scrollIntoView')
      .mockImplementation(() => {});

    const initial: ChatMessage[] = [
      { id: 1, role: 'user', content: 'Hi' },
      { id: 2, role: 'assistant', content: 'Hel' },
    ];
    const { rerender } = render(<ChatView messages={initial} />);
    expect(scrollSpy).toHaveBeenCalled();

    scrollSpy.mockClear();

    const streamed: ChatMessage[] = [
      { id: 1, role: 'user', content: 'Hi' },
      { id: 2, role: 'assistant', content: 'Hello there' },
    ];
    rerender(<ChatView messages={streamed} />);

    expect(scrollSpy).toHaveBeenCalled();
  });
});
