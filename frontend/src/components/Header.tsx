import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAppContext } from '@/contexts/AppContext';

const Header: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { getUsername, clearUser } = useAppContext();
  const isHome = location.pathname === '/';

  const handleLogout = () => {
    clearUser();
    navigate('/login', { replace: true });
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md border-b border-slate-200 shadow-sm">
      <div className="max-w-5xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
          <div className="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-700 rounded-lg flex items-center justify-center">
            <span className="text-white text-sm font-bold">AI</span>
          </div>
          <span className="font-semibold text-slate-800 hidden sm:inline">
            AI 智能刷题面试
          </span>
        </Link>

        <nav className="flex items-center gap-2">
          {!isHome && (
            <Link
              to="/"
              className="px-3 py-1.5 text-sm text-slate-600 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
            >
              首页
            </Link>
          )}
          <Link
            to="/history"
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              location.pathname.startsWith('/history')
                ? 'text-primary-600 bg-primary-50'
                : 'text-slate-600 hover:text-primary-600 hover:bg-primary-50'
            }`}
          >
            历史记录
          </Link>
          <Link
            to="/knowledge"
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              location.pathname.startsWith('/knowledge')
                ? 'text-amber-600 bg-amber-50'
                : 'text-slate-600 hover:text-amber-600 hover:bg-amber-50'
            }`}
          >
            知识库
          </Link>
          <span className="ml-2 px-3 py-1.5 text-sm text-slate-500 bg-slate-100 rounded-full">
            👤 {getUsername()}
          </span>
          <button
            onClick={handleLogout}
            className="ml-1 px-2 py-1.5 text-xs text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
            title="退出登录"
          >
            退出
          </button>
        </nav>
      </div>
    </header>
  );
};

export default Header;
