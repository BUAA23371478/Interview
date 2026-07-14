import React, { useReducer, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { interviewApi } from '@/api/interview';
import { interviewReducer, initialInterviewState } from '@/reducers/interviewReducer';
import { useInterviewSSE } from '@/hooks/useInterviewSSE';
import InterviewChat from '@/components/InterviewChat';
import InterviewInput from '@/components/InterviewInput';
import LoadingDots from '@/components/LoadingDots';

const InterviewSession: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [state, dispatch] = useReducer(interviewReducer, initialInterviewState);

  // Initialize session and connect SSE
  useEffect(() => {
    if (!sessionId) return;

    dispatch({
      type: 'SET_SESSION',
      payload: {
        sessionId,
        totalRounds: 10,
        jdContent: '',
        resumeContent: '',
      },
    });
  }, [sessionId]);

  // SSE connection
  useInterviewSSE(sessionId || '', dispatch);

  // Handle interview completion
  useEffect(() => {
    if (state.phase === 'completed' && sessionId) {
      navigate(`/interview/${sessionId}/report`, { replace: true });
    }
  }, [state.phase, sessionId, navigate]);

  const handleSubmitAnswer = useCallback(async () => {
    if (!state.userAnswer.trim() || !sessionId) return;

    dispatch({ type: 'SET_PHASE', payload: 'submitting' });

    try {
      await interviewApi.submitAnswer(sessionId, state.userAnswer);
      dispatch({ type: 'SET_USER_ANSWER', payload: '' });
    } catch (e: unknown) {
      const err = e as { message?: string };
      dispatch({ type: 'SET_ERROR', payload: err.message || '提交失败' });
    }
  }, [state.userAnswer, sessionId]);

  const canAnswer = state.phase === 'answering';
  const isSubmitting = state.phase === 'submitting';

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={() => navigate('/interview')}
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          重新设置
        </button>
        <div className="text-sm text-slate-400">
          第 <span className="font-semibold text-slate-700">{state.currentRound}</span>/{state.totalRounds} 轮
          {state.isFollowUp && (
            <span className="ml-2 text-purple-500 font-medium">· 追问中</span>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden mb-6">
        <div
          className="h-full bg-gradient-to-r from-purple-500 to-purple-700 rounded-full transition-all duration-500"
          style={{ width: `${(state.currentRound / state.totalRounds) * 100}%` }}
        />
      </div>

      {/* Chat messages */}
      <div className="mb-6">
        <InterviewChat
          messages={state.messages}
          isStreaming={state.isStreaming}
        />
      </div>

      {/* Waiting state */}
      {(state.phase === 'waiting_question' || state.phase === 'receiving_question') &&
        state.messages.length === 0 && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-center">
            <LoadingDots text="面试官正在准备第一个问题" className="justify-center mb-3" />
            <p className="text-sm text-slate-400">正在分析 JD 和简历，生成个性化面试问题...</p>
          </div>
      )}

      {/* Input area */}
      {state.phase !== 'completed' && state.phase !== 'generating_report' && state.phase !== 'error' && (
        <InterviewInput
          value={state.userAnswer}
          onChange={(value) => dispatch({ type: 'SET_USER_ANSWER', payload: value })}
          onSubmit={handleSubmitAnswer}
          disabled={!canAnswer}
          loading={isSubmitting}
          currentRound={state.currentRound}
          totalRounds={state.totalRounds}
        />
      )}

      {/* Generating report */}
      {state.phase === 'generating_report' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-center">
          <LoadingDots text="面试结束，正在生成复盘报告" className="justify-center mb-3" />
          <p className="text-sm text-slate-400">正在综合分析你的全部回答，生成多维度评估...</p>
        </div>
      )}

      {/* Error */}
      {state.phase === 'error' && state.error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center">
          <p className="text-red-600 mb-4">{state.error}</p>
          <button
            onClick={() => navigate('/interview')}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm transition-colors"
          >
            重新开始
          </button>
        </div>
      )}
    </div>
  );
};

export default InterviewSession;
