import type { ReactNode } from "react";

export function formatRichText(text: string): ReactNode[] {
  const raw = (text || "").trim();
  if (!raw) return [];

  const blocks = raw
    .split(/\n{2,}/)
    .map((b) => b.trim())
    .filter(Boolean);

  return blocks.map((block, i) => {
    const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
    return (
      <p key={i} className="rich-p">
        {lines.map((line, j) => (
          <span key={j}>
            {j > 0 && <br />}
            {formatInline(line)}
          </span>
        ))}
      </p>
    );
  });
}

function formatInline(line: string): ReactNode[] {
  const re =
    /(`[^`]+`)|(\b[a-zA-Z][a-zA-Z0-9_]*\s*=\s*[^\n,;]+)|(\b[a-zA-Z][a-zA-Z0-9_]*\^[0-9]+)|(\b(?:lr|lr0|lr_t|gamma|lambda|alpha|beta|eta)[a-zA-Z0-9_^]*)/g;

  const nodes: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) nodes.push(line.slice(last, m.index));
    const raw = m[0];
    const code = raw.startsWith("`") && raw.endsWith("`") ? raw.slice(1, -1) : raw.trim();
    nodes.push(
      <code key={`c${k++}`} className="inline-code">
        {code}
      </code>,
    );
    last = m.index + raw.length;
  }
  if (last < line.length) nodes.push(line.slice(last));
  return nodes.length ? nodes : [line];
}

export function splitPromptAndHints(
  prompt: string,
  hints: string[] | undefined,
): { prompt: string; hints: string[] } {
  const given = (hints || []).map((h) => h.trim()).filter(Boolean);
  if (given.length) {
    return { prompt: (prompt || "").trim(), hints: given };
  }

  const lines = (prompt || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) {
    return { prompt: (prompt || "").trim(), hints: [] };
  }

  const tipLike =
    /^(hint|tip|use |compute |think |remember |consider |try )/i;
  const body: string[] = [];
  const peeled: string[] = [];
  for (const line of lines) {
    if (tipLike.test(line) && body.length > 0) peeled.push(line.replace(/^(hint|tip)\s*[:.—-]\s*/i, ""));
    else body.push(line);
  }
  if (!peeled.length) {
    return { prompt: lines.join("\n\n"), hints: [] };
  }
  return { prompt: body.join("\n\n"), hints: peeled };
}
