import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkRehype from "remark-rehype";
import rehypeHighlight from "rehype-highlight";
import rehypeStringify from "rehype-stringify";

/**
 * Embedded CSS styles for the standalone HTML document.
 * Includes prose typography, syntax highlighting (GitHub theme), and custom styles.
 */
const EMBEDDED_STYLES = `
/* Base reset and typography */
*, *::before, *::after { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.6;
  color: #1a1a1a;
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
  background: #fff;
}

/* Headings */
h1, h2, h3, h4, h5, h6 {
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  font-weight: 600;
  line-height: 1.3;
}
h1 { font-size: 2em; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.3em; }
h3 { font-size: 1.25em; }
h4 { font-size: 1em; }

/* Paragraphs and inline */
p { margin: 1em 0; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
strong { font-weight: 600; }
code {
  background: #f3f4f6;
  padding: 0.2em 0.4em;
  border-radius: 3px;
  font-size: 0.875em;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

/* Code blocks */
pre {
  background: #f6f8fa;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 1em;
  overflow-x: auto;
  font-size: 0.875em;
  line-height: 1.5;
}
pre code {
  background: none;
  padding: 0;
  border-radius: 0;
  font-size: inherit;
}

/* Tables */
table {
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
}
th, td {
  border: 1px solid #d1d5db;
  padding: 0.5em 0.75em;
  text-align: left;
}
th { background: #f9fafb; font-weight: 600; }
tr:nth-child(even) { background: #f9fafb; }

/* Lists */
ul, ol { margin: 1em 0; padding-left: 2em; }
li { margin: 0.25em 0; }
li > ul, li > ol { margin: 0.25em 0; }

/* Task lists */
ul.contains-task-list { list-style: none; padding-left: 0; }
li.task-list-item { display: flex; align-items: baseline; gap: 0.5em; }
input[type="checkbox"] { margin: 0; }

/* Blockquotes */
blockquote {
  border-left: 4px solid #d1d5db;
  margin: 1em 0;
  padding: 0.5em 1em;
  color: #4b5563;
}

/* Horizontal rules */
hr { border: none; border-top: 1px solid #e5e7eb; margin: 2em 0; }

/* Images */
img { max-width: 100%; height: auto; }

/* Mermaid diagrams */
.mermaid-diagram {
  text-align: center;
  margin: 1.5em 0;
  overflow-x: auto;
}
.mermaid-error {
  border: 1px solid #fbbf24;
  background: #fffbeb;
  border-radius: 6px;
  padding: 1em;
  margin: 1em 0;
}
.mermaid-error p { margin: 0 0 0.5em; font-weight: 500; color: #92400e; }
.mermaid-error pre { background: #fffbeb; border-color: #fbbf24; color: #78350f; }

/* highlight.js GitHub theme */
.hljs{color:#24292e;background:#f6f8fa}
.hljs-doctag,.hljs-keyword,.hljs-meta .hljs-keyword,.hljs-template-tag,.hljs-template-variable,.hljs-type,.hljs-variable.language_{color:#d73a49}
.hljs-title,.hljs-title.class_,.hljs-title.class_.inherited__,.hljs-title.function_{color:#6f42c1}
.hljs-attr,.hljs-attribute,.hljs-literal,.hljs-meta,.hljs-number,.hljs-operator,.hljs-selector-attr,.hljs-selector-class,.hljs-selector-id,.hljs-variable{color:#005cc5}
.hljs-meta .hljs-string,.hljs-regexp,.hljs-string{color:#032f62}
.hljs-built_in,.hljs-symbol{color:#e36209}
.hljs-code,.hljs-comment,.hljs-formula{color:#6a737d}
.hljs-name,.hljs-quote,.hljs-selector-pseudo,.hljs-selector-tag{color:#22863a}
.hljs-subst{color:#24292e}
.hljs-section{color:#005cc5;font-weight:700}
.hljs-bullet{color:#735c0f}
.hljs-emphasis{color:#24292e;font-style:italic}
.hljs-strong{color:#24292e;font-weight:700}
.hljs-addition{color:#22863a;background-color:#f0fff4}
.hljs-deletion{color:#b31d28;background-color:#ffeef0}
`;

/**
 * Generates a self-contained HTML document from Markdown content.
 *
 * - Parses Markdown to HTML with GFM support
 * - Renders Mermaid code blocks as inline SVG
 * - Applies syntax highlighting to fenced code blocks via rehype-highlight
 * - Embeds all CSS styles inline (no external dependencies)
 * - Wraps output in a full HTML document
 */
export async function generateStandaloneHtml(
  markdownContent: string
): Promise<string> {
  // Step 1: Parse Markdown to HAST (HTML AST) with GFM and syntax highlighting
  const processor = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkRehype, { allowDangerousHtml: false })
    .use(rehypeHighlight, { detect: false, ignoreMissing: true })
    .use(rehypeStringify);

  const file = await processor.process(markdownContent);
  let htmlBody = String(file);

  // Step 2: Render Mermaid code blocks as inline SVG
  htmlBody = await renderMermaidBlocks(htmlBody);

  // Step 3: Assemble the full HTML document
  const fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tech Spec</title>
<style>${EMBEDDED_STYLES}</style>
</head>
<body>
${htmlBody}
</body>
</html>`;

  return fullHtml;
}

/**
 * Finds mermaid code blocks in the HTML output and replaces them with rendered SVG.
 * Mermaid code blocks appear as: <pre><code class="language-mermaid">...</code></pre>
 */
async function renderMermaidBlocks(html: string): Promise<string> {
  // Match <pre><code class="language-mermaid">...</code></pre> blocks
  const mermaidBlockRegex =
    /<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/gi;

  const matches = Array.from(html.matchAll(mermaidBlockRegex));

  if (matches.length === 0) {
    return html;
  }

  // Dynamically import mermaid for rendering
  const mermaid = (await import("mermaid")).default;
  mermaid.initialize({
    startOnLoad: false,
    theme: "default",
    securityLevel: "loose",
  });

  let result = html;

  for (let i = 0; i < matches.length; i++) {
    const match = matches[i];
    const rawCode = match[1];
    // Decode HTML entities that may have been escaped during markdown processing
    const mermaidCode = decodeHtmlEntities(rawCode);

    try {
      const id = `mermaid-svg-${Date.now()}-${i}`;
      const { svg } = await mermaid.render(id, mermaidCode);
      result = result.replace(
        match[0],
        `<div class="mermaid-diagram">${svg}</div>`
      );
    } catch {
      // Graceful degradation: show raw code with error note
      result = result.replace(
        match[0],
        `<div class="mermaid-error"><p>Diagram rendering error</p><pre><code>${rawCode}</code></pre></div>`
      );
    }
  }

  return result;
}

/**
 * Decodes common HTML entities back to their character equivalents.
 */
function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#x27;/g, "'")
    .replace(/&#x2F;/g, "/");
}

/**
 * Triggers a browser file download for the given content.
 *
 * Creates a Blob from the content, generates an object URL,
 * triggers download via a programmatic anchor click, then
 * revokes the object URL.
 */
export function downloadAsFile(
  content: string,
  filename: string,
  mimeType: string
): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);

  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";

  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);

  URL.revokeObjectURL(url);
}
