// Practice mode type definitions

export type PracticePhase =
  | 'loading_question'
  | 'answering'
  | 'submitting'
  | 'feedback_shown'
  | 'error';

export interface Question {
  id: string;
  content: string;
  type: 'short_answer' | 'choice';
  options?: string[];
}

export interface Feedback {
  score: number;
  isCorrect: boolean;
  correctAnswer: string;
  analysis: string;
  knowledgePoints: string[];
  commonMistakes: string[];
}

export interface PracticeState {
  phase: PracticePhase;
  sessionId: string;
  topic: string;
  currentQuestion: Question | null;
  userAnswer: string;
  feedback: Feedback | null;
  questionIndex: number;
  difficulty: number;
  consecutiveCorrect: number;
  consecutiveWrong: number;
  isStreaming: boolean;
  streamingContent: string;
  error: string | null;
  timeSpent: number;
  referenceAnswer: string;
  maxQuestions: number;
  completed: boolean;
}

export type PracticeAction =
  | { type: 'SET_SESSION'; payload: { sessionId: string; topic: string } }
  | { type: 'START_LOADING_QUESTION' }
  | { type: 'APPEND_QUESTION_CHUNK'; payload: string }
  | { type: 'SET_QUESTION'; payload: { question: Question; questionIndex: number; difficulty: number } }
  | { type: 'SET_USER_ANSWER'; payload: string }
  | { type: 'START_SUBMITTING' }
  | { type: 'APPEND_FEEDBACK_CHUNK'; payload: string }
  | { type: 'SET_FEEDBACK'; payload: { feedback: Feedback; consecutiveCorrect: number; consecutiveWrong: number } }
  | { type: 'SET_ERROR'; payload: string }
  | { type: 'NEXT_QUESTION' }
  | { type: 'SET_TIME_SPENT'; payload: number }
  | { type: 'SET_REFERENCE_ANSWER'; payload: string }
  | { type: 'SHOW_REFERENCE' }
  | { type: 'SET_MAX_QUESTIONS'; payload: number }
  | { type: 'SET_COMPLETED' };

export interface PracticeSessionSummary {
  sessionId: string;
  topic: string;
  totalQuestions: number;
  totalCorrect: number;
  accuracy: number;
  createdAt: string;
  status: string;
}

export interface PracticeRecord {
  id: string;
  sessionId: string;
  questionNumber: number;
  question: string;
  questionType: string;
  userAnswer: string;
  score: number;
  isCorrect: boolean;
  feedback: string;
  timeSpentSeconds: number;
  createdAt: string;
}

export interface PracticeSessionDetail {
  session: {
    id: string;
    topic: string;
    status: string;
    difficultyLevel: number;
    maxQuestions: number;
    totalQuestions: number;
    totalCorrect: number;
    createdAt: string;
  };
  records: PracticeRecord[];
}

export interface PracticeStats {
  totalQuestions: number;
  totalCorrect: number;
  overallAccuracy: number;
  weakTopics: Array<{
    topic: string;
    accuracy: number;
    totalQuestions: number;
  }>;
}
