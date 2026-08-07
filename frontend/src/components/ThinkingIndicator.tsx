import { useEffect, useState } from "react";

const FALLBACK_LINES = [
  "Thinking through your request",
  "Shaping a clear answer",
  "Pulling the right ideas together",
  "Almost ready",
];

const BY_LABEL: Record<string, string[]> = {
  Thinking: [
    "Thinking through your request",
    "Figuring out the best angle",
    "Shaping a clear answer",
  ],
  "Working on it": [
    "Working on it",
    "Agents are on the job",
    "Putting the pieces together",
  ],
  "Writing reply": [
    "Writing your reply",
    "Keeping it clear and focused",
    "Almost ready",
  ],
  "Starting path": [
    "Opening your study path",
    "Preparing the first lesson",
    "Getting ready to teach",
  ],
  "Next step": [
    "Loading the next step",
    "Preparing the next lesson",
    "Almost there",
  ],
  "Re-teaching": [
    "Re-teaching that idea",
    "Clearing up the confusion",
    "Building a simpler explanation",
  ],
  "Building quiz": [
    "Building your checkpoint quiz",
    "Writing fair questions",
    "Almost ready",
  ],
  "Grading quiz": [
    "Checking your answers",
    "Scoring the checkpoint",
    "Wrapping up",
  ],
  "Loading progress": [
    "Loading your progress",
    "Gathering streaks and scores",
  ],
};

type Props = {
  label?: string;
  compact?: boolean;
};

export function ThinkingIndicator({ label = "Thinking", compact = false }: Props) {
  const lines = BY_LABEL[label] || FALLBACK_LINES;
  const [i, setI] = useState(0);
  const [secs, setSecs] = useState(0);

  useEffect(() => {
    setI(0);
    setSecs(0);
    const rot = window.setInterval(() => setI((x) => (x + 1) % lines.length), 2200);
    const tick = window.setInterval(() => setSecs((s) => s + 1), 1000);
    return () => {
      window.clearInterval(rot);
      window.clearInterval(tick);
    };
  }, [label, lines.length]);

  const waitHint =
    secs < 4 ? "just a moment" : secs < 12 ? "still with you" : "hang tight — good answers take a beat";

  if (compact) {
    return (
      <span className="await-chip" aria-live="polite">
        <span className="think-orb" aria-hidden />
        <span className="think-copy">
          <span className="think-line">{lines[i]}</span>
        </span>
        <span className="think-dots" aria-hidden>
          <i />
          <i />
          <i />
        </span>
      </span>
    );
  }

  return (
    <div className="bubble agent thinking enter" aria-live="polite">
      <div className="think-row">
        <span className="think-orb" aria-hidden />
        <div className="think-copy">
          <div className="think-line">{lines[i]}</div>
          <div className="think-sub">{waitHint}</div>
        </div>
        <span className="think-dots" aria-hidden>
          <i />
          <i />
          <i />
        </span>
      </div>
      <div className="think-bar" aria-hidden>
        <span />
      </div>
    </div>
  );
}
