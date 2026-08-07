import type { DailyConcept, PracticeProblem } from "./types";
import { USER } from "./types";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}

export const api = {
  tracks: () => req<{ tracks: string[] }>("/api/arena/tracks"),
  dailyConcept: () => req<DailyConcept>("/api/daily"),
  dailyProblem: () => req<PracticeProblem>("/api/arena/daily"),
  generateProblem: () =>
    req<PracticeProblem>("/api/arena/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }),
  submitPractice: (problemId: string, answer: string) =>
    req<{
      score: number;
      passed: boolean;
      feedback: string;
      explanation?: string;
      correct_key?: string | null;
      format?: string;
    }>("/api/arena/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: USER, problem_id: problemId, answer }),
    }),
  rate: (targetType: string, targetId: string, score: number, comment?: string) =>
    req<{ id: string; score: number }>("/api/ratings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: USER,
        target_type: targetType,
        target_id: targetId,
        score,
        comment: comment || null,
      }),
    }),
  ratingSummary: (targetType: string, targetId: string) =>
    req<{
      average: number | null;
      count: number;
      mine: { score: number; comment?: string } | null;
    }>(
      `/api/ratings/summary?target_type=${encodeURIComponent(targetType)}&target_id=${encodeURIComponent(targetId)}&user_id=${USER}`,
    ),
};
