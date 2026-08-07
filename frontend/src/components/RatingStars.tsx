import { useEffect, useState } from "react";
import { api } from "../api";

type Props = {
  targetType: string;
  targetId: string;
  label?: string;
};

export function RatingStars({ targetType, targetId, label = "Rate this" }: Props) {
  const [mine, setMine] = useState(0);
  const [avg, setAvg] = useState<number | null>(null);
  const [count, setCount] = useState(0);
  const [hover, setHover] = useState(0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!targetId) return;
    let cancelled = false;
    api
      .ratingSummary(targetType, targetId)
      .then((s) => {
        if (cancelled) return;
        setAvg(s.average);
        setCount(s.count);
        setMine(s.mine?.score || 0);
      })
      .catch((e) => {
        console.log("rating summary failed", e);
      });
    return () => {
      cancelled = true;
    };
  }, [targetType, targetId]);

  async function pick(score: number) {
    if (!targetId || saving) return;
    setSaving(true);
    setMine(score);
    try {
      await api.rate(targetType, targetId, score);
      const s = await api.ratingSummary(targetType, targetId);
      setAvg(s.average);
      setCount(s.count);
    } catch (e) {
      console.log("rating save failed", e);
    } finally {
      setSaving(false);
    }
  }

  if (!targetId) return null;

  const shown = hover || mine;

  return (
    <div className="rating" aria-label={label}>
      <span className="rating-label">{label}</span>
      <div className="stars" onMouseLeave={() => setHover(0)}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={`star ${n <= shown ? "on" : ""}`}
            onMouseEnter={() => setHover(n)}
            onClick={() => pick(n)}
            disabled={saving}
            aria-label={`${n} stars`}
          >
            ★
          </button>
        ))}
      </div>
      <span className="rating-meta">
        {count > 0 && avg != null ? `${avg.toFixed(1)} · ${count}` : ""}
      </span>
    </div>
  );
}
