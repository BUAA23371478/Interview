import React from 'react';

interface LoadingDotsProps {
  text?: string;
  className?: string;
}

const LoadingDots: React.FC<LoadingDotsProps> = ({ text = '加载中', className = '' }) => {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="inline-flex gap-1">
        <span
          className="w-2 h-2 bg-primary-400 rounded-full animate-pulse-dot"
          style={{ animationDelay: '0s' }}
        />
        <span
          className="w-2 h-2 bg-primary-400 rounded-full animate-pulse-dot"
          style={{ animationDelay: '0.2s' }}
        />
        <span
          className="w-2 h-2 bg-primary-400 rounded-full animate-pulse-dot"
          style={{ animationDelay: '0.4s' }}
        />
      </span>
      <span className="text-sm text-slate-400">{text}...</span>
    </div>
  );
};

export default LoadingDots;
