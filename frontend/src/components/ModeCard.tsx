import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Pencil, Target } from 'lucide-react';

interface ModeCardProps {
  mode: 'practice' | 'interview';
}

const config = {
  practice: {
    icon: Pencil,
    title: '刷题模式',
    description: '输入主题，逐题练习，即时反馈',
    features: ['自由输入练习主题', '逐题作答即时评分', '难度自适应调节', '历史记录与薄弱分析'],
    buttonText: '开始刷题',
    to: '/practice',
    gradient: 'from-blue-500 to-blue-700',
    bgGradient: 'from-blue-50 to-blue-100',
    borderHover: 'hover:border-blue-300',
    iconBg: 'bg-blue-100',
    iconColor: 'text-blue-600',
    buttonBg: 'bg-blue-600 hover:bg-blue-700',
  },
  interview: {
    icon: Target,
    title: '模拟面试模式',
    description: 'JD + 简历，模拟面试，整体复盘',
    features: ['粘贴目标岗位 JD', '上传个人简历', '自定义面试轮数', '多维度复盘报告'],
    buttonText: '开始面试',
    to: '/interview',
    gradient: 'from-purple-500 to-purple-700',
    bgGradient: 'from-purple-50 to-purple-100',
    borderHover: 'hover:border-purple-300',
    iconBg: 'bg-purple-100',
    iconColor: 'text-purple-600',
    buttonBg: 'bg-purple-600 hover:bg-purple-700',
  },
};

const ModeCard: React.FC<ModeCardProps> = ({ mode }) => {
  const navigate = useNavigate();
  const c = config[mode];
  const Icon = c.icon;

  return (
    <div
      className={`
        relative overflow-hidden rounded-2xl border-2 border-slate-200 ${c.borderHover}
        bg-white shadow-sm hover:shadow-lg transition-all duration-300
        flex flex-col p-6 sm:p-8 cursor-pointer
      `}
      onClick={() => navigate(c.to)}
    >
      {/* Decorative gradient blob */}
      <div className={`absolute -top-10 -right-10 w-32 h-32 bg-gradient-to-br ${c.gradient} rounded-full opacity-10`} />

      <div className="relative z-10 flex-1">
        <div className={`inline-flex p-3 rounded-xl ${c.iconBg} mb-4`}>
          <Icon className={`w-7 h-7 ${c.iconColor}`} />
        </div>

        <h3 className="text-xl font-bold text-slate-800 mb-2">{c.title}</h3>
        <p className="text-slate-500 text-sm mb-4">{c.description}</p>

        <ul className="space-y-2 mb-6">
          {c.features.map((feature) => (
            <li key={feature} className="flex items-start gap-2 text-sm text-slate-600">
              <svg className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              {feature}
            </li>
          ))}
        </ul>
      </div>

      <button
        className={`relative z-10 w-full py-3 ${c.buttonBg} text-white font-medium rounded-xl transition-all duration-200 active:scale-95`}
      >
        {c.buttonText}
      </button>
    </div>
  );
};

export default ModeCard;
