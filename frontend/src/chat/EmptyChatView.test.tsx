import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EmptyChatView } from './EmptyChatView';
import { SUGGESTIONS } from './suggestions';

afterEach(() => {
  cleanup();
});

describe('EmptyChatView', () => {
  it('marks the container with data-state="empty"', () => {
    render(<EmptyChatView />);
    const container = screen.getByRole('region', { name: /start a new chat/i });
    expect(container).toHaveAttribute('data-state', 'empty');
  });

  it('renders all four suggestion bubbles', () => {
    render(<EmptyChatView />);
    for (const s of SUGGESTIONS) {
      expect(screen.getByRole('button', { name: s })).toBeInTheDocument();
    }
    expect(SUGGESTIONS).toHaveLength(4);
  });

  it('clicking a suggestion bubble populates the input', async () => {
    const user = userEvent.setup();
    render(<EmptyChatView />);

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
    render(<EmptyChatView onSubmit={onSubmit} />);

    const input = screen.getByRole('textbox', { name: /message/i });
    await user.type(input, '   hi there   ');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith('hi there');
  });

  it('disables Send when input is empty or whitespace', async () => {
    const user = userEvent.setup();
    render(<EmptyChatView />);
    const send = screen.getByRole('button', { name: /^send$/i });
    expect(send).toBeDisabled();

    await user.type(screen.getByRole('textbox', { name: /message/i }), '   ');
    expect(send).toBeDisabled();
  });
});
