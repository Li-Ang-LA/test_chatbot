import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AssistantMarkdown } from './AssistantMarkdown';

afterEach(() => {
  cleanup();
});

describe('AssistantMarkdown', () => {
  it('strips <script> tags from model output', () => {
    const malicious = 'Hi <script>alert(1)</script> there';
    const { container } = render(<AssistantMarkdown content={malicious} />);
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).toContain('Hi');
    expect(container.textContent).toContain('there');
  });

  it('strips onerror attributes from images', () => {
    const payload = '![x](x.png "t")\n\n<img src="x" onerror="alert(1)" />';
    const { container } = render(<AssistantMarkdown content={payload} />);
    for (const img of container.querySelectorAll('img')) {
      expect(img.hasAttribute('onerror')).toBe(false);
    }
  });

  it('renders a fenced code block as <pre><code class="language-..."> with hljs markup', () => {
    const md = '```js\nconst x = 1;\n```';
    const { container } = render(<AssistantMarkdown content={md} />);

    const code = container.querySelector('pre code');
    expect(code).not.toBeNull();
    expect(code!.className).toMatch(/language-js/);
    expect(code!.className).toMatch(/hljs/);
  });

  it('renders a GFM table as a <table>', () => {
    const md = '| a | b |\n| - | - |\n| 1 | 2 |\n';
    const { container } = render(<AssistantMarkdown content={md} />);

    const table = container.querySelector('table');
    expect(table).not.toBeNull();
    const headers = table!.querySelectorAll('th');
    expect(headers).toHaveLength(2);
    expect(headers[0].textContent).toBe('a');
    const cells = table!.querySelectorAll('tbody td');
    expect(cells).toHaveLength(2);
    expect(cells[1].textContent).toBe('2');
  });

  it('copies code to clipboard when the Copy button is clicked', async () => {
    const user = userEvent.setup();
    const writeText = vi
      .spyOn(navigator.clipboard, 'writeText')
      .mockResolvedValue(undefined);
    render(<AssistantMarkdown content={'```\nhello world\n```'} />);

    await user.click(screen.getByRole('button', { name: /copy code/i }));
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText.mock.calls[0][0]).toContain('hello world');
  });
});
