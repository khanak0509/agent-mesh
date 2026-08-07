import type { ReactNode } from "react";

export function Markdown({ text }: { text: string }) {
  const src = (text || "").replace(/\r\n/g, "\n").trim();
  if (!src) return null;

  const blocks = splitBlocks(src);
  return (
    <div className="md">
      {blocks.map((b, i) => (
        <Block key={i} block={b} />
      ))}
    </div>
  );
}

type Block =
  | { type: "h"; level: number; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "code"; lang: string; code: string }
  | { type: "quote"; text: string }
  | { type: "p"; text: string };

function splitBlocks(src: string): Block[] {
  const lines = src.split("\n");
  const out: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (/^```/.test(line)) {
      const lang = line.replace(/^```/, "").trim();
      const buf: string[] = [];
      i += 1;
      while (i < lines.length && !/^```/.test(lines[i])) {
        buf.push(lines[i]);
        i += 1;
      }
      out.push({ type: "code", lang, code: buf.join("\n") });
      i += 1;
      continue;
    }

    const hm = /^(#{1,3})\s+(.+)$/.exec(line);
    if (hm) {
      out.push({ type: "h", level: hm[1].length, text: hm[2] });
      i += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const buf: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^>\s?/, ""));
        i += 1;
      }
      out.push({ type: "quote", text: buf.join("\n") });
      continue;
    }

    if (/^\s*([-*•]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\.\s+/.test(line);
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*•]|\d+\.)\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*•]|\d+\.)\s+/, ""));
        i += 1;
      }
      out.push({ type: ordered ? "ol" : "ul", items });
      continue;
    }

    if (!line.trim()) {
      i += 1;
      continue;
    }

    const buf: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^```/.test(lines[i]) &&
      !/^#{1,3}\s+/.test(lines[i]) &&
      !/^>\s?/.test(lines[i]) &&
      !/^\s*([-*•]|\d+\.)\s+/.test(lines[i])
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    out.push({ type: "p", text: buf.join(" ") });
  }

  return out;
}

function Block({ block }: { block: Block }) {
  if (block.type === "h") {
    const Tag = (`h${Math.min(block.level + 2, 5)}` as "h3" | "h4" | "h5");
    return (
      <Tag className={`md-h md-h${block.level}`}>{inline(block.text)}</Tag>
    );
  }
  if (block.type === "ul") {
    return (
      <ul className="md-ul">
        {block.items.map((it, i) => (
          <li key={i}>{inline(it)}</li>
        ))}
      </ul>
    );
  }
  if (block.type === "ol") {
    return (
      <ol className="md-ol">
        {block.items.map((it, i) => (
          <li key={i}>{inline(it)}</li>
        ))}
      </ol>
    );
  }
  if (block.type === "code") {
    return (
      <pre className="md-pre">
        <code>{block.code}</code>
      </pre>
    );
  }
  if (block.type === "quote") {
    return <blockquote className="md-quote">{inline(block.text)}</blockquote>;
  }
  return <p className="md-p">{inline(block.text)}</p>;
}

function inline(text: string): ReactNode[] {
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_)/g;
  const nodes: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const raw = m[0];
    if (raw.startsWith("`")) {
      nodes.push(
        <code key={k++} className="inline-code">
          {raw.slice(1, -1)}
        </code>,
      );
    } else if (raw.startsWith("**")) {
      nodes.push(<strong key={k++}>{raw.slice(2, -2)}</strong>);
    } else {
      nodes.push(<em key={k++}>{raw.slice(1, -1)}</em>);
    }
    last = m.index + raw.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length ? nodes : [text];
}
