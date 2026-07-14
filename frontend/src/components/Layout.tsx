import React from 'react';
import { Outlet } from 'react-router-dom';
import Header from './Header';

const Layout: React.FC = () => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      <Header />
      <main className="pt-16">
        <Outlet />
      </main>
      <footer className="py-6 text-center text-sm text-slate-400">
        AI 智能刷题与模拟面试系统 · 助力技术面试备考
      </footer>
    </div>
  );
};

export default Layout;
