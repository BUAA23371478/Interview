import React, { useReducer, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { practiceApi } from '@/api/practice';
import { practiceReducer, initialPracticeState } from '@/reducers/practiceReducer';
import { usePracticeSSE } from '@/hooks/usePracticeSSE';
import { useCountdown } from '@/hooks/useCountdown';
import QuestionCard from '@/components/QuestionCard';
import AnswerInput from '@/components/AnswerInput';
import FeedbackPanel from '@/components/FeedbackPanel';
import DifficultyBadge from '@/components/DifficultyBadge';
import LoadingDots from '@/components/LoadingDots';

const PracticeSession: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [state, dispatch] = useReducer(practiceReducer, initialPracticeState);
  const { elapsed, start, stop, formatTime } = useCountdown();

  const topic = (location.state as { topic?: string })?.topic || '';

  // Initialize session
  useEffect(() => {
    if (sessionId) {
      dispatch({
        type: 'SET_SESSION',
        payload: { sessionId, topic },
      });
    }
  }, [sessionId, topic]);

  // SSE connection
  usePracticeSSE(sessionId || '', dispatch);

  // Start timer when question is shown
  useEffect(() => {
    if (state.phase === 'answering' && state.currentQuestion) {
      start();
    }
  }, [state.phase, state.currentQuestion, start]);

  const handleSubmitAnswer = useCallback(async () => {
    if (!state.userAnswer.trim() || !sessionId) return;

    const timeSpent = stop();
    dispatch({ type: 'SET_TIME_SPENT', payload: timeSpent });
    dispatch({ type: 'START_SUBMITTING' });

    try {
      await practiceApi.submitAnswer(sessionId, state.userAnswer, timeSpent);
    } catch (e: unknown) {
      const err = e as { message?: string };
      dispatch({ type: 'SET_ERROR', payload: err.message || '提交失败' });
    }
  }, [state.userAnswer, sessionId, stop]);

  const handleSkipQuestion = useCallback(async () => {
    if (!sessionId) return;
    dispatch({ type: 'START_SUBMITTING' });
    try {
      await practiceApi.skipQuestion(sessionId);
    } catch (e: unknown) {
      const err = e as { message?: string };
      dispatch({ type: 'SET_ERROR', payload: err.message || '操作失败' });
    }
  }, [sessionId]);

  const handleNextQuestion = useCallback(async () => {
    if (!sessionId) return;

    dispatch({ type: 'NEXT_QUESTION' });

    try {
      await practiceApi.nextQuestion(sessionId);
    } catch (e: unknown) {
      const err = e as { message?: string };
      dispatch({ type: 'SET_ERROR', payload: err.message || '获取题目失败' });
    }
  }, [sessionId]);

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={() => navigate('/history/practice')}
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          退出练习
        </button>
        <div className="flex items-center gap-4">
          {state.maxQuestions > 0 && (
            <span className="text-sm font-medium text-slate-600 bg-slate-100 px-3 py-1 rounded-full">
              第 {Math.min(state.questionIndex, state.maxQuestions)}/{state.maxQuestions} 题
            </span>
          )}
          <span className="text-sm text-slate-400">
            {topic}
          </span>
        </div>
      </div>

      {/* Completed banner */}
      {state.completed && state.phase === 'feedback_shown' && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-2xl text-center">
          <p className="text-green-700 font-medium">🎉 本会话已完成！共 {state.maxQuestions} 题</p>
          <button
            onClick={() => navigate(`/history/practice/${sessionId}`)}
            className="mt-2 text-sm text-green-600 hover:underline"
          >
            查看历史记录
          </button>
        </div>
      )}

      {/* Difficulty Indicator */}
      {state.currentQuestion && (
        <div className="mb-6">
          <DifficultyBadge
            difficulty={state.difficulty}
            questionIndex={state.questionIndex}
            consecutiveCorrect={state.consecutiveCorrect}
            consecutiveWrong={state.consecutiveWrong}
          />
        </div>
      )}

      {/* Timer */}
      {state.phase === 'answering' && (
        <div className="flex items-center justify-end mb-4">
          <span className="text-sm text-slate-400 bg-slate-100 px-3 py-1 rounded-full">
            ⏱ {formatTime(elapsed)}
          </span>
        </div>
      )}

      {/* Loading state */}
      {state.phase === 'loading_question' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-12 flex flex-col items-center justify-center">
          <LoadingDots text="AI 正在生成题目" className="mb-3" />
          {state.streamingContent && (
            <div className="mt-4 text-sm text-slate-500 max-w-md text-center">
              {state.streamingContent.slice(0, 100)}...
            </div>
          )}
        </div>
      )}

      {/* Question — shown during answering, submitting, and feedback */}
      {(state.phase === 'answering' || state.phase === 'submitting' || state.phase === 'feedback_shown') &&
        state.currentQuestion && (
          <div className="mb-6">
            <QuestionCard
              question={state.currentQuestion}
              questionIndex={state.questionIndex}
            />
          </div>
      )}

      {/* Answer Input */}
      {state.phase === 'answering' && (
        <>
          <AnswerInput
            value={state.userAnswer}
            onChange={(value) => dispatch({ type: 'SET_USER_ANSWER', payload: value })}
            onSubmit={handleSubmitAnswer}
            disabled={false}
            loading={false}
          />
          <div className="flex justify-center mt-3">
            <button
              onClick={handleSkipQuestion}
              className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            >
              不了解，查看参考答案
            </button>
          </div>
        </>
      )}

      {/* Submitting */}
      {state.phase === 'submitting' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-center">
          <LoadingDots text="AI 正在评估你的答案" className="justify-center mb-3" />
          {state.streamingContent && (
            <div className="mt-4 p-4 bg-slate-50 rounded-xl text-left">
              <div className="text-sm text-slate-600 whitespace-pre-wrap">
                {state.streamingContent}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Feedback: Your Answer + Reference Answer + Next */}
      {state.phase === 'feedback_shown' && state.feedback && (
        <div className="space-y-4">
          {/* User's Answer */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
            <h4 className="font-semibold text-slate-800 mb-3">📝 你的答案</h4>
            <div className="text-sm text-slate-600 whitespace-pre-wrap">
              {state.userAnswer || '(未作答)'}
            </div>
          </div>

          {/* Reference Answer */}
          <FeedbackPanel feedback={state.feedback} />

          <div className="flex justify-center pt-2">
            <button
              onClick={handleNextQuestion}
              className="flex items-center gap-2 px-6 py-3 bg-primary-600 hover:bg-primary-700 text-white font-medium rounded-xl transition-all duration-200 active:scale-95 shadow-sm"
            >
              下一题
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {state.phase === 'error' && state.error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center">
          <p className="text-red-600 mb-4">{state.error}</p>
          <button
            onClick={() => {
              dispatch({ type: 'NEXT_QUESTION' });
              handleNextQuestion();
            }}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm transition-colors"
          >
            重试
          </button>
        </div>
      )}
    </div>
  );
};

export default PracticeSession;
