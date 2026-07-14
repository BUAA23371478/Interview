import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAppContext } from '@/contexts/AppContext';
import { userApi } from '@/api/history';

const RegisterPage: React.FC = () => {
  const { setUser } = useAppContext();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleRegister = async () => {
    const trimmedName = username.trim();
    const trimmedPwd = password.trim();

    if (!trimmedName) {
      setError('请输入用户名');
      return;
    }
    if (trimmedName.length > 20) {
      setError('用户名请控制在20字以内');
      return;
    }
    if (!trimmedPwd) {
      setError('请输入密码');
      return;
    }
    if (trimmedPwd.length < 3) {
      setError('密码至少3位（开发环境简写）');
      return;
    }
    if (trimmedPwd !== confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const user = await userApi.register(trimmedName, trimmedPwd);
      setUser(user);
      navigate('/', { replace: true });
    } catch (e: unknown) {
      const err = e as { message?: string; status?: number };
      if (err.status === 409) {
        setError('用户名已存在，请换个用户名或直接登录');
      } else {
        setError(err.message || '注册失败，请重试');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-blue-50 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex w-14 h-14 bg-gradient-to-br from-primary-500 to-primary-700 rounded-2xl items-center justify-center mb-4">
            <span className="text-white text-2xl font-bold">AI</span>
          </div>
          <h1 className="text-xl font-bold text-slate-800">AI 智能刷题与模拟面试</h1>
          <p className="text-sm text-slate-500 mt-1">注册新账号</p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <input
            type="text"
            value={username}
            onChange={(e) => { setUsername(e.target.value); setError(''); }}
            placeholder="用户名"
            maxLength={20}
            disabled={loading}
            className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all mb-3"
            autoFocus
          />

          <input
            type="password"
            value={password}
            onChange={(e) => { setPassword(e.target.value); setError(''); }}
            placeholder="密码（至少3位）"
            maxLength={100}
            disabled={loading}
            className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all mb-3"
          />

          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => { setConfirmPassword(e.target.value); setError(''); }}
            onKeyDown={(e) => e.key === 'Enter' && handleRegister()}
            placeholder="确认密码"
            maxLength={100}
            disabled={loading}
            className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
          />

          {error && (
            <p className="text-sm text-red-500 text-center mt-3">{error}</p>
          )}

          <button
            onClick={handleRegister}
            disabled={loading || !username.trim() || !password.trim() || !confirmPassword.trim()}
            className="w-full mt-4 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-all duration-200 active:scale-95"
          >
            {loading ? '注册中...' : '注册'}
          </button>

          <p className="text-center text-sm text-slate-500 mt-4">
            已有账号？{' '}
            <Link to="/login" className="text-primary-600 hover:text-primary-700 font-medium">
              去登录
            </Link>
          </p>
        </div>

        <p className="text-center text-xs text-slate-400 mt-4">
          开发环境 · 数据仅保存在本地
        </p>
      </div>
    </div>
  );
};

export default RegisterPage;
