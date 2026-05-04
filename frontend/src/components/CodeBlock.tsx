"use client";

import { cn } from "@/lib/utils";

export interface CodeBlockProps {
  children: string;
  language?: string;
  className?: string;
}

/**
 * Renders a code block with syntax highlighting.
 * rehype-highlight applies highlight.js classes during Markdown rendering,
 * so this component provides the styled container and copy affordance.
 */
export function CodeBlock({ children, language, className }: CodeBlockProps) {
  return (
    <div className={cn("relative my-4 rounded-lg border bg-muted", className)}>
      {language && (
        <div className="flex items-center justify-between border-b px-4 py-2">
          <span className="text-xs font-medium text-muted-foreground">{language}</span>
        </div>
      )}
      <pre className="overflow-x-auto p-4">
        <code className={language ? `hljs language-${language}` : "hljs"}>
          {children}
        </code>
      </pre>
    </div>
  );
}
