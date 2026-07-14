import { useEffect, useRef, useCallback } from 'react';
import type { InterviewAction, InterviewMessage } from '@/types/interview';
import { createSSEConnection } from '@/api/sse';

let idCounter = 0;
function genId(): string {
  return `msg_${++idCounter}_${Date.now()}`;
}

export function useInterviewSSE(
  sessionId: string,
  dispatch: React.Dispatch<InterviewAction>
) {
  const closeRef = useRef<(() => void) | null>(null);

  const connect = useCallback(() => {
    if (!sessionId) return;

    closeRef.current?.();

    const cleanup = createSSEConnection(
      `/interview/${sessionId}/stream`,
      {
        onEvent: (eventType: string, data: string) => {
          try {
            const parsed = JSON.parse(data);

            switch (eventType) {
              case 'interview_started':
                break;

              case 'question_start': {
                const msg: InterviewMessage = {
                  id: genId(),
                  role: 'interviewer',
                  content: '',
                  round: parsed.round,
                  isFollowUp: parsed.isFollowUp || false,
                  isStreaming: true,
                };
                dispatch({ type: 'ADD_MESSAGE', payload: msg });
                dispatch({ type: 'SET_PHASE', payload: 'receiving_question' });
                break;
              }

              case 'question_chunk':
                dispatch({ type: 'APPEND_TO_LAST_MESSAGE', payload: parsed.content || '' });
                break;

              case 'question_done': {
                // Mark last message as done streaming
                dispatch({ type: 'SET_PHASE', payload: 'answering' });
                dispatch({ type: 'SET_STREAMING', payload: false });
                break;
              }

              case 'feedback_start': {
                const msg: InterviewMessage = {
                  id: genId(),
                  role: 'interviewer',
                  content: '',
                  isStreaming: true,
                };
                dispatch({ type: 'ADD_MESSAGE', payload: msg });
                break;
              }

              case 'feedback_chunk':
                dispatch({ type: 'APPEND_TO_LAST_MESSAGE', payload: parsed.content || '' });
                break;

              case 'feedback_done': {
                dispatch({ type: 'SET_STREAMING', payload: false });
                if (parsed.action === 'follow_up') {
                  dispatch({ type: 'INCREMENT_FOLLOW_UP' });
                  dispatch({ type: 'SET_IS_FOLLOW_UP', payload: true });
                } else if (parsed.action === 'next_round') {
                  dispatch({ type: 'SET_IS_FOLLOW_UP', payload: false });
                }
                break;
              }

              case 'follow_up': {
                dispatch({ type: 'INCREMENT_FOLLOW_UP' });
                dispatch({ type: 'SET_IS_FOLLOW_UP', payload: true });
                break;
              }

              case 'round_advanced':
                dispatch({ type: 'SET_CURRENT_ROUND', payload: parsed.round });
                dispatch({ type: 'SET_IS_FOLLOW_UP', payload: false });
                break;

              case 'report_generating':
                dispatch({ type: 'SET_PHASE', payload: 'generating_report' });
                break;

              case 'report_chunk':
                // Report generation is handled on the report page
                break;

              case 'report_done':
              case 'interview_complete':
                dispatch({ type: 'SET_PHASE', payload: 'completed' });
                break;

              case 'error':
                dispatch({ type: 'SET_ERROR', payload: parsed.message || '面试过程发生错误' });
                break;

              default:
                break;
            }
          } catch {
            // Ignore parse errors
          }
        },
        onFatal: () => {
          dispatch({ type: 'SET_ERROR', payload: '连接中断，请刷新页面重试' });
        },
      }
    );

    closeRef.current = cleanup;
  }, [sessionId, dispatch]);

  useEffect(() => {
    connect();
    return () => {
      closeRef.current?.();
    };
  }, [connect]);

  return { reconnect: connect };
}
