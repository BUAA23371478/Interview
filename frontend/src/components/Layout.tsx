import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { authApi, UserInfo } from '../api/auth'

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `px-3 py-2 rounded-lg text-sm font-medium transition ${
          isActive ? 'bg-purple-100 text-purple-700' : 'text-gray-600 hover:bg-gray-100'
        }`
      }
    >
      {label}
    </NavLink>
  )
}

export default function Layout() {
  const [user, setUser] = useState<UserInfo | null>(null)

  useEffect(() => {
    authApi.me().then(setUser).catch(() => {})
  }, [])

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-lg border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center space-x-3">
            <div className="w-9 h-9 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-800">AI 面试智能体</h1>
              <p className="text-xs text-gray-500">模拟面试 · 专项练习 · 知识库</p>
            </div>
          </Link>
          <nav className="flex items-center space-x-1">
            <NavItem to="/" label="首页" />
            <NavItem to="/interview/setup" label="模拟面试" />
            <NavItem to="/practice/setup" label="专项练习" />
            <NavItem to="/knowledge" label="知识库" />
            {user?.is_admin && <NavItem to="/review" label="审核中心" />}
            <NavItem to="/profile" label="个人中心" />
          </nav>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-8"><Outlet /></main>
    </div>
  )
}
