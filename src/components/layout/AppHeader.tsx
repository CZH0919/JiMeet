import { Bell, ChevronDown, LogOut, Plus, ShieldAlert, User as UserIcon } from 'lucide-react';
import { useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { clsx } from 'clsx';
import { ROLE_LABEL } from '@/domain/labels';
import { useAuth } from '@/features/useAuth';
import { useUnreadCount } from '@/features/useNotifications';
import { Logo } from './Logo';
import { NotificationDrawer } from './NotificationDrawer';

const NAV = [
  { to: '/', label: '首页', end: true },
  { to: '/jobs', label: '招聘' },
  { to: '/me', label: '个人中心' },
  { to: '/messages', label: '消息' },
];

export function AppHeader() {
  const { user, logout } = useAuth();
  const unread = useUnreadCount();
  const [menuOpen, setMenuOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = async () => {
    setMenuOpen(false);
    await logout();
    navigate('/login');
  };

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4">
        <Logo />

        <nav className="flex flex-1 items-center gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx(
                  'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary-soft text-primary' : 'text-ink2 hover:bg-page hover:text-ink',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
          {user?.isAdmin && (
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                clsx(
                  'ml-2 flex items-center gap-1 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-danger-soft text-danger' : 'text-danger hover:bg-danger-soft',
                )
              }
            >
              <ShieldAlert size={15} /> 管理员后台
            </NavLink>
          )}
        </nav>

        <div className="flex items-center gap-3">
          {user && (
            <Link
              to="/jobs/new"
              className="inline-flex h-9 items-center gap-1 rounded-md bg-primary px-4 text-sm font-medium text-white hover:bg-primary-hover"
            >
              <Plus size={16} /> 发布招聘
            </Link>
          )}

          <button
            onClick={() => setDrawerOpen(true)}
            className="relative rounded-md p-2 text-ink2 hover:bg-page hover:text-ink"
            aria-label="通知"
          >
            <Bell size={20} />
            {unread > 0 && (
              <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-medium text-white">
                {unread > 99 ? '99+' : unread}
              </span>
            )}
          </button>

          {user ? (
            <div className="relative">
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 rounded-md py-1 pl-1 pr-2 hover:bg-page"
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-soft text-sm font-medium text-primary">
                  {user.name[0]}
                </span>
                <span className="text-sm font-medium text-ink">{user.name}</span>
                <ChevronDown size={15} className="text-muted" />
              </button>

              {menuOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                  <div className="absolute right-0 top-11 z-20 w-60 rounded-lg border border-line bg-surface py-2 shadow-pop">
                    <div className="border-b border-line px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-ink">{user.name}</span>
                        <span className="rounded-full bg-primary-soft px-2 py-0.5 text-xs text-primary">
                          {ROLE_LABEL[user.role]}
                        </span>
                        {user.isAdmin && (
                          <span className="rounded-full bg-danger-soft px-2 py-0.5 text-xs text-danger">
                            管理员
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-xs text-ink2">
                        {user.role === 'student' ? '学号' : '工号'} {user.id} · {user.college}
                      </div>
                    </div>
                    <Link
                      to="/me"
                      onClick={() => setMenuOpen(false)}
                      className="flex items-center gap-2 px-4 py-2.5 text-sm text-ink hover:bg-page"
                    >
                      <UserIcon size={16} /> 个人主页
                    </Link>
                    <Link
                      to="/notifications"
                      onClick={() => setMenuOpen(false)}
                      className="flex items-center gap-2 px-4 py-2.5 text-sm text-ink hover:bg-page"
                    >
                      <Bell size={16} /> 通知中心
                    </Link>
                    <button
                      onClick={handleLogout}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-danger hover:bg-danger-soft"
                    >
                      <LogOut size={16} /> 退出登录
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <Link to="/login" className="text-sm font-medium text-primary hover:underline">
              登录
            </Link>
          )}
        </div>
      </div>

      <NotificationDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </header>
  );
}
