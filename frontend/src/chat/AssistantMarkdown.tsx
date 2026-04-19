import { useState } from 'react';
import type { ComponentPropsWithoutRef, ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import 'highlight.js/styles/github.css';

const schema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [['className']],
    pre: [['className']],
    span: [['className']],
  },
};

function childrenToString(children: ReactNode): string {
  if (children == null || typeof children === 'boolean') return '';
  if (typeof children === 'string' || typeof children === 'number') {
    return String(children);
  }
  if (Array.isArray(children)) return children.map(childrenToString).join('');
  if (typeof children === 'object' && 'props' in children) {
    const node = children as { props?: { children?: ReactNode } };
    return childrenToString(node.props?.children);
  }
  return '';
}

function CodeCopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label="Copy code"
      className="absolute top-2 right-2 rounded-md border border-neutral-200 bg-white/90 px-2 py-1 text-xs text-neutral-600 shadow-sm hover:bg-neutral-50"
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function Pre({ children, ...rest }: ComponentPropsWithoutRef<'pre'>) {
  const code = childrenToString(children);
  return (
    <div className="relative my-4">
      <pre
        {...rest}
        className="overflow-x-auto rounded-xl bg-neutral-950 p-4 text-sm text-neutral-100"
      >
        {children}
      </pre>
      <CodeCopyButton code={code} />
    </div>
  );
}

type Props = { content: string };

export function AssistantMarkdown({ content }: Props) {
  return (
    <div className="prose prose-neutral max-w-none text-base leading-relaxed text-neutral-800">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight, [rehypeSanitize, schema]]}
        components={{ pre: Pre }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
