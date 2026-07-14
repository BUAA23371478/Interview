import React from 'react';
import type { Question } from '@/types/practice';
import MarkdownContent from '@/utils/markdown';

interface QuestionCardProps {
  question: Question;
  questionIndex: number;
}

const QuestionCard: React.FC<QuestionCardProps> = ({ question, questionIndex }) => {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 animate-slide-up">
      <div className="flex items-center gap-3 mb-4">
        <span className="inline-flex items-center justify-center w-8 h-8 bg-primary-100 text-primary-700 rounded-full text-sm font-semibold">
          {questionIndex}
        </span>
        <span className="text-sm text-slate-400 font-medium">
          第 {questionIndex} 题
        </span>
        <span className="px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-500 rounded-full">
          {question.type === 'choice' ? '选择题' : '简答题'}
        </span>
      </div>

      <div className="mb-4 select-none" onCopy={(e) => e.preventDefault()}>
        <MarkdownContent content={question.content} />
      </div>

      {question.type === 'choice' && question.options && (
        <div className="space-y-2 mt-4">
          {question.options.map((option, index) => (
            <div
              key={index}
              className="flex items-center gap-3 p-3 rounded-xl border border-slate-200 bg-slate-50 hover:bg-white hover:border-primary-300 transition-colors cursor-pointer"
            >
              <span className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-sm font-semibold">
                {String.fromCharCode(65 + index)}
              </span>
              <span className="text-slate-700">{option}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default QuestionCard;
