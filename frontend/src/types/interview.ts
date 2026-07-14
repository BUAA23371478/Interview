// Interview mode type definitions

export type InterviewPhase =
  | 'setup'
  | 'waiting_question'
  | 'receiving_question'
  | 'answering'
  | 'submitting'
  | 'completed'
  | 'generating_report'
  | 'error';

export interface InterviewMessage {
  id: string;
  role: 'interviewer' | 'user' | 'system';
  content: string;
  round?: number;
  isFollowUp?: boolean;
  isStreaming?: boolean;
}

export interface InterviewState {
  phase: InterviewPhase;
  sessionId: string;
  jdContent: string;
  resumeContent: string;
  totalRounds: number;
  currentRound: number;
  isFollowUp: boolean;
  followUpCount: number;
  messages: InterviewMessage[];
  userAnswer: string;
  isStreaming: boolean;
  streamingContent: string;
  error: string | null;
}

export type InterviewAction =
  | { type: 'SET_SESSION'; payload: { sessionId: string; totalRounds: number; jdContent: string; resumeContent: string } }
  | { type: 'SET_PHASE'; payload: InterviewPhase }
  | { type: 'ADD_MESSAGE'; payload: InterviewMessage }
  | { type: 'APPEND_TO_LAST_MESSAGE'; payload: string }
  | { type: 'SET_USER_ANSWER'; payload: string }
  | { type: 'SET_STREAMING'; payload: boolean }
  | { type: 'SET_CURRENT_ROUND'; payload: number }
  | { type: 'SET_IS_FOLLOW_UP'; payload: boolean }
  | { type: 'INCREMENT_FOLLOW_UP' }
  | { type: 'SET_ERROR'; payload: string }
  | { type: 'RESET' }
  | { type: 'SET_INITIAL_MESSAGE'; payload: string };

export interface DimensionScores {
  techDepth: number;
  clarity: number;
  logic: number;
  jobMatch: number;
}

export interface RoundReview {
  round: number;
  question: string;
  answerSummary: string;
  comment: string;
}

export interface Highlight {
  round: number;
  reason: string;
}

export interface InterviewReport {
  overallScore: number;
  dimensions: DimensionScores;
  overallComment: string;
  roundReviews: RoundReview[];
  highlights: Highlight[];
  weaknesses: string[];
  suggestions: string[];
}

export interface InterviewSessionSummary {
  sessionId: string;
  jdContent: string;
  resumeContent: string;
  totalRounds: number;
  completedRounds: number;
  overallScore: number | null;
  status: string;
  createdAt: string;
}

export interface InterviewQA {
  id: string;
  roundNumber: number;
  isFollowUp: boolean;
  question: string;
  userAnswer: string | null;
  aiFeedback: string | null;
  createdAt: string;
}

export interface InterviewSessionDetail {
  session: {
    id: string;
    jdContent: string;
    resumeContent: string;
    totalRounds: number;
    completedRounds: number;
    overallScore: number | null;
    status: string;
    createdAt: string;
  };
  qaRecords: InterviewQA[];
  report: InterviewReport | null;
}
