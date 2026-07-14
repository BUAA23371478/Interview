import type { InterviewState, InterviewAction, InterviewMessage } from '@/types/interview';

export const initialInterviewState: InterviewState = {
  phase: 'setup',
  sessionId: '',
  jdContent: '',
  resumeContent: '',
  totalRounds: 10,
  currentRound: 1,
  isFollowUp: false,
  followUpCount: 0,
  messages: [],
  userAnswer: '',
  isStreaming: false,
  streamingContent: '',
  error: null,
};

let messageIdCounter = 0;
function generateMessageId(): string {
  return `msg_${++messageIdCounter}_${Date.now()}`;
}

export function interviewReducer(state: InterviewState, action: InterviewAction): InterviewState {
  switch (action.type) {
    case 'SET_SESSION':
      return {
        ...state,
        sessionId: action.payload.sessionId,
        totalRounds: action.payload.totalRounds,
        jdContent: action.payload.jdContent,
        resumeContent: action.payload.resumeContent,
        phase: 'waiting_question',
        messages: [],
        currentRound: 1,
        isFollowUp: false,
        followUpCount: 0,
        error: null,
      };

    case 'SET_PHASE':
      return {
        ...state,
        phase: action.payload,
      };

    case 'ADD_MESSAGE':
      return {
        ...state,
        messages: [...state.messages, action.payload],
      };

    case 'APPEND_TO_LAST_MESSAGE': {
      const messages = [...state.messages];
      if (messages.length > 0) {
        const last = { ...messages[messages.length - 1] };
        last.content += action.payload;
        messages[messages.length - 1] = last;
      }
      return { ...state, messages };
    }

    case 'SET_USER_ANSWER':
      return {
        ...state,
        userAnswer: action.payload,
      };

    case 'SET_STREAMING':
      return {
        ...state,
        isStreaming: action.payload,
      };

    case 'SET_CURRENT_ROUND':
      return {
        ...state,
        currentRound: action.payload,
      };

    case 'SET_IS_FOLLOW_UP':
      return {
        ...state,
        isFollowUp: action.payload,
      };

    case 'INCREMENT_FOLLOW_UP':
      return {
        ...state,
        followUpCount: state.followUpCount + 1,
      };

    case 'SET_INITIAL_MESSAGE': {
      const msg: InterviewMessage = {
        id: generateMessageId(),
        role: 'interviewer',
        content: action.payload,
        round: state.currentRound,
        isStreaming: false,
      };
      return {
        ...state,
        messages: [...state.messages, msg],
      };
    }

    case 'SET_ERROR':
      return {
        ...state,
        phase: 'error',
        error: action.payload,
        isStreaming: false,
      };

    case 'RESET':
      return {
        ...initialInterviewState,
      };

    default:
      return state;
  }
}
