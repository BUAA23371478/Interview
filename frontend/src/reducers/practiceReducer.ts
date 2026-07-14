import type { PracticeState, PracticeAction } from '@/types/practice';

export const initialPracticeState: PracticeState = {
  phase: 'loading_question',
  sessionId: '',
  topic: '',
  currentQuestion: null,
  userAnswer: '',
  feedback: null,
  questionIndex: 0,
  difficulty: 3,
  consecutiveCorrect: 0,
  consecutiveWrong: 0,
  isStreaming: false,
  streamingContent: '',
  error: null,
  timeSpent: 0,
  referenceAnswer: '',
  maxQuestions: 20,
  completed: false,
};

export function practiceReducer(state: PracticeState, action: PracticeAction): PracticeState {
  switch (action.type) {
    case 'SET_SESSION':
      return {
        ...state,
        sessionId: action.payload.sessionId,
        topic: action.payload.topic,
        phase: 'loading_question',
      };

    case 'START_LOADING_QUESTION':
      return {
        ...state,
        phase: 'loading_question',
        isStreaming: true,
        streamingContent: '',
        currentQuestion: null,
        userAnswer: '',
        feedback: null,
        error: null,
      };

    case 'APPEND_QUESTION_CHUNK':
      return {
        ...state,
        streamingContent: state.streamingContent + action.payload,
      };

    case 'SET_QUESTION':
      return {
        ...state,
        phase: 'answering',
        isStreaming: false,
        currentQuestion: action.payload.question,
        questionIndex: action.payload.questionIndex,
        difficulty: action.payload.difficulty,
        streamingContent: '',
      };

    case 'SET_USER_ANSWER':
      return {
        ...state,
        userAnswer: action.payload,
      };

    case 'START_SUBMITTING':
      return {
        ...state,
        phase: 'submitting',
        isStreaming: true,
        streamingContent: '',
      };

    case 'APPEND_FEEDBACK_CHUNK':
      return {
        ...state,
        streamingContent: state.streamingContent + action.payload,
      };

    case 'SET_FEEDBACK':
      return {
        ...state,
        phase: 'feedback_shown',
        isStreaming: false,
        feedback: action.payload.feedback,
        consecutiveCorrect: action.payload.consecutiveCorrect,
        consecutiveWrong: action.payload.consecutiveWrong,
        streamingContent: '',
      };

    case 'SET_ERROR':
      return {
        ...state,
        phase: 'error',
        isStreaming: false,
        error: action.payload,
      };

    case 'NEXT_QUESTION':
      return {
        ...state,
        phase: 'loading_question',
        currentQuestion: null,
        userAnswer: '',
        feedback: null,
        streamingContent: '',
      };

    case 'SET_TIME_SPENT':
      return {
        ...state,
        timeSpent: action.payload,
      };

    case 'SET_REFERENCE_ANSWER':
      return {
        ...state,
        referenceAnswer: action.payload,
      };

    case 'SHOW_REFERENCE':
      return {
        ...state,
        phase: 'feedback_shown',
        isStreaming: false,
        streamingContent: '',
        feedback: {
          score: 0,
          isCorrect: false,
          correctAnswer: state.referenceAnswer || '暂无参考答案',
          analysis: '',
          knowledgePoints: [],
          commonMistakes: [],
        },
      };

    case 'SET_MAX_QUESTIONS':
      return { ...state, maxQuestions: action.payload };

    case 'SET_COMPLETED':
      return { ...state, completed: true };

    default:
      return state;
  }
}
