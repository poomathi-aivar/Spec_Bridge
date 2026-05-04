"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";

export interface SectionNavItem {
  id: string;
  text: string;
  level: number;
}

export interface SectionNavProps {
  markdown: string;
  className?: string;
}

/**
 * Generates a table of contents sidebar from Markdown headings.
 * Parses heading lines (# through ####) and renders anchor links.
 */
export function SectionNav({ markdown, className }: SectionNavProps) {
  const headings = useMemo(() => extractHeadings(markdown), [markdown]);

  if (headings.length === 0) {
    return null;
  }

  return (
    <nav
      className={cn("sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto", className)}
      aria-label="Table of contents"
    >
      <h2 className="mb-3 text-sm font-semibold text-foreground">Contents</h2>
      <ul className="space-y-1">
        {headings.map((heading) => (
          <li key={heading.id}>
            <a
              href={`#${heading.id}`}
              className={cn(
                "block text-sm text-muted-foreground transition-colors hover:text-foreground",
                heading.level === 1 && "font-medium",
                heading.level === 2 && "pl-3",
                heading.level === 3 && "pl-6",
                heading.level >= 4 && "pl-9"
              )}
            >
              {heading.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/**
 * Extracts headings from raw Markdown text.
 * Matches lines starting with 1-6 `#` characters.
 */
export function extractHeadings(markdown: string): SectionNavItem[] {
  const headingRegex = /^(#{1,6})\s+(.+)$/gm;
  const headings: SectionNavItem[] = [];
  let match: RegExpExecArray | null;

  while ((match = headingRegex.exec(markdown)) !== null) {
    const level = match[1].length;
    const text = match[2].trim();
    const id = text
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/\s+/g, "-");

    headings.push({ id, text, level });
  }

  return headings;
}
