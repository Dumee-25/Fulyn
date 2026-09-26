import { Fragment } from "react";

/**
 * Renders the small markdown subset our reports use: #/## headings, "- " bullets,
 * **bold** and paragraphs. Text is rendered as React text, never as HTML.
 */
function inline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-medium text-foreground">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

export function Markdown({ source }: { source: string }) {
  const blocks: React.ReactNode[] = [];
  let bullets: string[] = [];

  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={blocks.length} className="mb-4 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {bullets.map((b, i) => (
            <li key={i}>{inline(b)}</li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };

  for (const line of source.split("\n")) {
    if (line.startsWith("- ")) {
      bullets.push(line.slice(2));
      continue;
    }
    flush();
    if (line.startsWith("## ")) {
      blocks.push(
        <h3 key={blocks.length} className="mt-5 mb-2 text-sm font-medium">
          {line.slice(3)}
        </h3>,
      );
    } else if (line.startsWith("# ")) {
      blocks.push(
        <h2 key={blocks.length} className="mb-3 text-lg font-semibold tracking-tight">
          {line.slice(2)}
        </h2>,
      );
    } else if (line.trim()) {
      blocks.push(
        <p key={blocks.length} className="mb-3 text-sm leading-relaxed">
          {inline(line)}
        </p>,
      );
    }
  }
  flush();
  return <div>{blocks}</div>;
}
