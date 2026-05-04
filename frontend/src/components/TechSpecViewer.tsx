"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { MermaidDiagram } from "@/components/MermaidDiagram";
import { cn } from "@/lib/utils";
import type { Components } from "react-markdown";

export interface TechSpecViewerProps {
  markdownContent: string;
  className?: string;
}

/**
 * Renders the generated tech spec Markdown with:
 * - GFM support (tables, strikethrough, task lists)
 * - Syntax highlighting for code blocks via rehype-highlight
 * - Mermaid diagram rendering for ```mermaid code blocks
 * - Heading IDs for section navigation anchors
 */
export function TechSpecViewer({ markdownContent, className }: TechSpecViewerProps) {
  return (
    <article
      className={cn("prose prose-sm dark:prose-invert max-w-none overflow-x-auto", className)}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={markdownComponents}
      >
        {markdownContent}
      </ReactMarkdown>
    </article>
  );
}

/**
 * Custom component overrides for react-markdown.
 */
const markdownComponents: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || "");
    const language = match ? match[1] : undefined;
    const codeContent = String(children).replace(/\n$/, "");

    // Detect if this is an inline code element (no language class and short content)
    const isInline = !className && !codeContent.includes("\n");

    if (isInline) {
      return (
        <code className="rounded bg-muted px-1.5 py-0.5 text-sm" {...props}>
          {children}
        </code>
      );
    }

    // Render Mermaid diagrams with the MermaidDiagram component
    if (language === "mermaid") {
      return <MermaidDiagram chart={codeContent} />;
    }

    // For other code blocks, render with language label
    return (
      <div className="relative my-4 rounded-lg border bg-muted">
        {language && (
          <div className="flex items-center justify-between border-b px-4 py-2">
            <span className="text-xs font-medium text-muted-foreground">{language}</span>
          </div>
        )}
        <pre className="overflow-x-auto p-4">
          <code className={className} {...props}>
            {children}
          </code>
        </pre>
      </div>
    );
  },

  // Add IDs to headings for section navigation
  h1({ children, ...props }) {
    const id = getHeadingId(children);
    return <h1 id={id} {...props}>{children}</h1>;
  },
  h2({ children, ...props }) {
    const id = getHeadingId(children);
    return <h2 id={id} {...props}>{children}</h2>;
  },
  h3({ children, ...props }) {
    const id = getHeadingId(children);
    return <h3 id={id} {...props}>{children}</h3>;
  },
  h4({ children, ...props }) {
    const id = getHeadingId(children);
    return <h4 id={id} {...props}>{children}</h4>;
  },
  h5({ children, ...props }) {
    const id = getHeadingId(children);
    return <h5 id={id} {...props}>{children}</h5>;
  },
  h6({ children, ...props }) {
    const id = getHeadingId(children);
    return <h6 id={id} {...props}>{children}</h6>;
  },
};

/**
 * Generates a URL-safe ID from heading children content.
 */
function getHeadingId(children: React.ReactNode): string {
  const text = getTextContent(children);
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-");
}

/**
 * Recursively extracts text content from React children.
 */
function getTextContent(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(getTextContent).join("");
  if (children && typeof children === "object" && "props" in children) {
    return getTextContent((children as React.ReactElement).props.children);
  }
  return "";
}
