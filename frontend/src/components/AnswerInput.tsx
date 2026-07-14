import React from 'react';
import { Send } from 'lucide-react';

interface AnswerInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  loading: boolean;
  placeholder?: string;
}

const AnswerInput: React.FC<AnswerInputProps> = ({
  value,
  onChange,
  onSubmit,
  disabled,
  loading,
  placeholder = '请输入你的答案...',
}) => {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 animate-slide-up">
      <label className="block text-sm font-medium text-slate-700 mb-2">
        你的回答
      </label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onPaste={(e) => { e.preventDefault(); }}
        placeholder={placeholder}
        disabled={disabled}
        rows={6}
        maxLength={2000}
        className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all resize-none disabled:opacity-50 disabled:cursor-not-allowed"
      />
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs text-slate-400">
          {value.length}/2000 · Ctrl+Enter 提交
        </span>
        <button
          onClick={onSubmit}
          disabled={disabled || loading || !value.trim()}
          className="flex items-center gap-2 px-5 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-all duration-200 active:scale-95"
        >
          {loading ? (
            <>
              <LoadingDotsSmall />
              提交中...
            </>
          ) : (
            <>
              <Send className="w-4 h-4" />
              提交答案
            </>
          )}
        </button>
      </div>
    </div>
  );
};

const LoadingDotsSmall: React.FC = () => (
  <span className="inline-flex gap-1">
    <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0s' }} />
    <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0.2s' }} />
    <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0.4s' }} />
  </span>
);

export default AnswerInput;
