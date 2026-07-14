import React, { useEffect, useState } from 'react';
import { HashRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AppProvider, useAppContext } from '@/contexts/AppContext';
import Layout from '@/components/Layout';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import HomePage from '@/pages/HomePage';
import PracticeSetup from '@/pages/PracticeSetup';
import PracticeSession from '@/pages/PracticeSession';
import PracticeDetail from '@/pages/PracticeDetail';
import InterviewSetup from '@/pages/InterviewSetup';
import InterviewSession from '@/pages/InterviewSession';
import InterviewReport from '@/pages/InterviewReport';
import HistoryOverview from '@/pages/HistoryOverview';
import PracticeHistory from '@/pages/PracticeHistory';
import InterviewHistory from '@/pages/InterviewHistory';
import InterviewDetail from '@/pages/InterviewDetail';

/**
 * 路由守卫：未登录重定向到 /login
 */
const AuthGuard: React.FC = () => {
  const { state, setUser } = useAppContext();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const existingUserId = localStorage.getItem('userId');
    const existingUsername = localStorage.getItem('username');
    if (existingUserId && existingUsername) {
      setUser({ userId: existingUserId, username: existingUsername });
    }
    setChecking(false);
  }, [setUser]);

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-blue-50">
        <div className="text-slate-400">加载中...</div>
      </div>
    );
  }

  if (!state.isRegistered) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
};

/**
 * 已登录时访问 /login 或 /register 自动跳回首页
 */
const GuestOnly: React.FC = () => {
  const { state } = useAppContext();
  if (state.isRegistered) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
};

const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* 公开路由：仅未登录可访问 */}
      <Route element={<GuestOnly />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      {/* 受保护路由：需登录 */}
      <Route element={<AuthGuard />}>
        <Route element={<Layout />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/practice" element={<PracticeSetup />} />
          <Route path="/practice/:sessionId" element={<PracticeSession />} />
          <Route path="/interview" element={<InterviewSetup />} />
          <Route path="/interview/:sessionId" element={<InterviewSession />} />
          <Route path="/interview/:sessionId/report" element={<InterviewReport />} />
          <Route path="/history" element={<HistoryOverview />} />
          <Route path="/history/practice" element={<PracticeHistory />} />
          <Route path="/history/practice/:sessionId" element={<PracticeDetail />} />
          <Route path="/history/interview" element={<InterviewHistory />} />
          <Route path="/history/interview/:id" element={<InterviewDetail />} />
        </Route>
      </Route>

      {/* 兜底 */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

const App: React.FC = () => {
  return (
    <HashRouter>
      <AppProvider>
        <AppRoutes />
      </AppProvider>
    </HashRouter>
  );
};

export default App;
