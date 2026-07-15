import { useEffect, useRef, useCallback } from 'react';
import type { PracticeAction } from '@/types/practice';
import { createSSEConnection } from '@/api/sse';

export function usePracticeSSE(
  sessionId: string,
  dispatch: React.Dispatch<PracticeAction>
) {
  const closeRef = useRef<(() => void) | null>(null);

  const connect = useCallback(() => {
    if (!sessionId) return;

    // Clean up previous connection
    closeRef.current?.();

    const cleanup = createSSEConnection(
      `/practice/${sessionId}/stream`,
      {
        onEvent: (eventType: string, data: string) => {
          try {
            const parsed = JSON.parse(data);

            switch (eventType) {
              case 'question_chunk':
                dispatch({ type: 'APPEND_QUESTION_CHUNK', payload: parsed.content || '' });
                break;

              case 'question_done':
                dispatch({
                  type: 'SET_QUESTION',
                  payload: {
                    question: {
                      id: parsed.question?.id || `q_${Date.now()}`,
                      content: parsed.question?.content || '',
                      type: parsed.question?.type || 'short_answer',
                      options: parsed.question?.options,
                    },
                    questionIndex: parsed.questionIndex ?? 0,
                    difficulty: parsed.difficulty ?? 3,
                  },
                });
                if (parsed.referenceAnswer) {
                  dispatch({ type: 'SET_REFERENCE_ANSWER', payload: parsed.referenceAnswer });
                }
                break;

              case 'feedback_chunk':
                dispatch({ type: 'APPEND_FEEDBACK_CHUNK', payload: parsed.content || '' });
                break;

              case 'feedback_done':
                dispatch({
                  type: 'SET_FEEDBACK',
                  payload: {
                    feedback: {
                      score: parsed.score ?? parsed.feedback?.score ?? 0,
                      isCorrect: parsed.is_correct ?? parsed.feedback?.isCorrect ?? false,
                      correctAnswer: parsed.feedback?.correctAnswer || '',
                      analysis: parsed.feedback?.analysis || '',
                      knowledgePoints: parsed.feedback?.knowledgePoints || [],
                      commonMistakes: parsed.feedback?.commonMistakes || [],
                    },
                    consecutiveCorrect: parsed.consecutiveCorrect ?? 0,
                    consecutiveWrong: parsed.consecutiveWrong ?? 0,
                  },
                });
                if (parsed.completed) {
                  dispatch({ type: 'SET_COMPLETED' });
                }
                break;

              case 'session_ready':
                if (parsed.maxQuestions) {
                  dispatch({ type: 'SET_MAX_QUESTIONS', payload: parsed.maxQuestions });
                }
                break;

              case 'session_completed':
                dispatch({ type: 'SET_COMPLETED' });
                break;

              case 'question_start':
                dispatch({ type: 'START_LOADING_QUESTION' });
                break;

              case 'error':
                dispatch({ type: 'SET_ERROR', payload: parsed.message || '发生错误' });
                break;

              default:
                break;
            }
          } catch {
            // Ignore parse errors for ping/keepalive events
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
