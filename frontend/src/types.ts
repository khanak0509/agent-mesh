export const USER = "demo-user";

export type Tab = "path" | "quiz" | "cards" | "arena" | "daily" | "progress";

export type PlanStep = {
  kind: string;
  title: string;
  topic: string;
  goal: string;
};

export type StudyPlan = {
  plan_id: string;
  topic: string;
  title: string;
  summary: string;
  steps: PlanStep[];
  status: string;
  current_step: number;
};

export type QuizOption = { label: string; text: string };
export type QuizQuestion = {
  question: string;
  options: QuizOption[];
  correct: string;
  explanation?: string;
};

export type QuizPayload = {
  quiz_id: string;
  topic: string;
  questions: QuizQuestion[];
  auto_from_study?: boolean;
  plan_id?: string;
  plan_step?: number;
};

export type Flashcard = {
  id?: string;
  front: string;
  back: string;
  hint?: string | null;
  topic?: string;
};

export type PracticeOption = { label: string; text: string };

export type PracticeProblem = {
  id: string;
  track: string;
  difficulty: string;
  format: "mcq" | "short" | "code" | string;
  title: string;
  prompt: string;
  options?: PracticeOption[];
  hints: string[];
  tags: string[];
  is_daily?: boolean;
  slug_day?: string | null;
};

export type DailyConcept = {
  id: string;
  day: string;
  track: string;
  title: string;
  body: string;
  why_it_matters: string;
  try_this: string;
};

export type WsMsg = {
  type: string;
  request_id?: string;
  intent?: string;
  content?: string;
  token?: string;
  payload?: Record<string, unknown>;
  status?: string;
  error?: string;
  detail?: string;
  note?: string;
  kind?: string;
  action?: string;
};
