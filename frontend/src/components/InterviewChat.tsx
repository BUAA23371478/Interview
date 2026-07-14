import React, { useRef, useEffect } from 'react';
import type { InterviewMessage } from '@/types/interview';
import MarkdownContent from '@/utils/markdown';
import LoadingDots from './LoadingDots';

interface InterviewChatProps {
  messages: InterviewMessage[];
  isStreaming: boolean;
}

const InterviewChat: React.FC<InterviewChatProps> = ({ messages, isStreaming }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-center">
          <LoadingDots text="面试官正在准备问题" />
          <p className="text-sm text-slate-400 mt-4">请稍候，正在根据 JD 和简历分析...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-slide-up`}
        >
          <div
            className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-5 py-4 ${
              msg.role === 'user'
                ? 'bg-primary-600 text-white'
                : msg.role === 'system'
                  ? 'bg-slate-100 text-slate-600'
                  : 'bg-white border border-slate-200 shadow-sm'
            }`}
          >
            {msg.role === 'interviewer' && (
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 bg-purple-100 rounded-full flex items-center justify-center">
                  <span className="text-purple-600 text-xs font-bold">AI</span>
                </div>
                <span className="text-xs font-medium text-purple-600">
                  面试官
                  {msg.round && ` · 第${msg.round}轮`}
                  {msg.isFollowUp && ' · 追问'}
                </span>
              </div>
            )}
            {msg.role === 'user' && (
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-medium text-blue-200">我的回答</span>
              </div>
            )}
            {msg.role === 'interviewer' ? (
              <MarkdownContent
                content={msg.content || (msg.isStreaming ? '...' : '')}
                className="prose-sm"
              />
            ) : (
              <p className="text-sm whitespace-pre-wrap leading-relaxed">
                {msg.content || (msg.isStreaming ? '...' : '')}
              </p>
            )}
            {msg.isStreaming && (
              <span className="inline-block w-2 h-4 bg-purple-400 animate-pulse ml-1" />
            )}
          </div>
        </div>
      ))}

      {isStreaming && (
        <div className="flex justify-start">
          <div className="bg-white border border-slate-200 rounded-2xl px-5 py-3 shadow-sm">
            <LoadingDots text="正在生成" />
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
};

export default InterviewChat;
