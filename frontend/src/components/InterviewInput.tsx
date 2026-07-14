import React from 'react';
import { Send } from 'lucide-react';

interface InterviewInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  loading: boolean;
  currentRound: number;
  totalRounds: number;
}

const InterviewInput: React.FC<InterviewInputProps> = ({
  value,
  onChange,
  onSubmit,
  disabled,
  loading,
  currentRound,
  totalRounds,
}) => {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-2">
        <label className="text-sm font-medium text-slate-700">
          第 {currentRound}/{totalRounds} 轮回答
        </label>
        <div className="w-32 h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-primary-500 rounded-full transition-all duration-500"
            style={{ width: `${(currentRound / totalRounds) * 100}%` }}
          />
        </div>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? '正在等待面试官提问...' : '请输入你的回答...'}
        disabled={disabled}
        rows={5}
        maxLength={3000}
        className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all resize-none disabled:opacity-50 disabled:cursor-not-allowed"
      />
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs text-slate-400">
          {value.length}/3000 · Ctrl+Enter 提交
        </span>
        <button
          onClick={onSubmit}
          disabled={disabled || loading || !value.trim()}
          className="flex items-center gap-2 px-5 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-all duration-200 active:scale-95"
        >
          {loading ? (
            <>
              <span className="inline-flex gap-1">
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0s' }} />
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0.2s' }} />
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0.4s' }} />
              </span>
              提交中...
            </>
          ) : (
            <>
              <Send className="w-4 h-4" />
              提交回答
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export default InterviewInput;
