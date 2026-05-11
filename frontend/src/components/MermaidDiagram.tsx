"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export interface MermaidDiagramProps {
  chart: string;
  className?: string;
}

/**
 * Renders a Mermaid diagram on the client side.
 * Uses dynamic import to avoid SSR issues with mermaid.js.
 */
export function MermaidDiagram({ chart, className }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function renderDiagram() {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "neutral",
          securityLevel: "loose",
          themeVariables: {
            lineColor: "#374151",
            primaryColor: "#e0e7ff",
            primaryTextColor: "#1f2937",
            primaryBorderColor: "#6366f1",
            secondaryColor: "#f3e8ff",
            tertiaryColor: "#ecfdf5",
          },
        });

        const id = `mermaid-${Math.random().toString(36).slice(2, 11)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart);

        if (!cancelled) {
          setSvg(renderedSvg);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to render diagram");
          setSvg("");
        }
      }
    }

    renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (error) {
    return (
      <div
        className={cn(
          "rounded-md border border-yellow-200 bg-yellow-50 p-4 dark:border-yellow-800 dark:bg-yellow-950",
          className
        )}
        role="alert"
      >
        <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
          Diagram rendering error
        </p>
        <pre className="mt-2 overflow-x-auto text-xs text-yellow-700 dark:text-yellow-300">
          {chart}
        </pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div
        className={cn("flex items-center justify-center p-8 text-muted-foreground", className)}
        aria-label="Loading diagram"
      >
        <span className="text-sm">Rendering diagram…</span>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={cn("overflow-x-auto rounded-lg border bg-white p-4 dark:bg-gray-50", className)}
      dangerouslySetInnerHTML={{ __html: svg }}
      aria-label="Mermaid diagram"
    />
  );
}
