import { ChevronDown, LogOut, Plus, ShieldAlert, UserRound } from 'lucide-react';
import { useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { clsx } from 'clsx';
import { ROLE_LABEL } from '@/domain/labels';
import { useAuth } from '@/features/useAuth';
import { useUnreadCount } from '@/features/useNotifications';
import { Logo } from './Logo';
import { NotificationBell } from './NotificationBell';

/** 主导航：站内通知不再占用导航项，改为头像左侧的小喇叭（见 NotificationBell） */
const NAV = [
  { to: '/', label: '首页', end: true },
  { to: '/jobs', label: '招聘' },
  { to: '/me', label: '个人中心' },
  { to: '/messages', label: '消息' },
];

export function AppHeader() {
  const { user, logout } = useAuth();
  const { count: unread, refresh: refreshUnread } = useUnreadCount();
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = async () => {
    setMenuOpen(false);
    await logout();
    navigate('/login');
  };

  return (
    <header className="sticky top-0 z-40 border-b border-line/80 bg-surface">
      <div className="page-shell flex h-[72px] items-center gap-2 sm:gap-4 lg:gap-8">
        <Logo />

        <nav className="flex flex-1 items-center gap-2.5 overflow-x-auto sm:gap-5 lg:gap-7">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx(
                  'relative whitespace-nowrap py-2 text-[13px] transition-colors sm:text-[15px]',
                  isActive ? 'font-semibold text-ink' : 'text-ink2 hover:text-ink',
                )
              }
            >
              {({ isActive }) => (
                <>
                  {item.label}
                  {isActive && (
                    <span className="absolute inset-x-0 bottom-0 mx-auto h-[3px] w-5 rounded-full bg-primary" />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3">
          {user && (
            <Link
              to="/jobs/new"
              className="hidden h-9 items-center gap-1 rounded-full bg-primary px-4 text-sm font-medium text-white shadow-[0_10px_24px_-14px_rgba(47,107,255,0.95)] transition-colors hover:bg-primary-hover sm:inline-flex"
            >
              <Plus size={16} /> 发布招聘
            </Link>
          )}

          {/* 小喇叭：站内通知（用户头像左侧） */}
          <NotificationBell unread={unread} onRead={() => void refreshUnread()} />

          {user ? (
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 rounded-full border border-line bg-surface py-1 pl-1 pr-2 transition-colors hover:border-primary/30 sm:pr-2.5"
                aria-expanded={menuOpen}
                aria-label="账号菜单"
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary">
                  {user.name.slice(0, 1)}
                </span>
                <span className="hidden max-w-[7rem] truncate text-sm font-medium text-ink sm:block">
                  {user.name}
                </span>
                <ChevronDown
                  size={15}
                  className={clsx('hidden text-muted transition-transform sm:block', menuOpen && 'rotate-180')}
                />
              </button>

              {menuOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                  <div className="absolute right-0 top-[calc(100%+10px)] z-20 w-60 animate-fade-in rounded-lg border border-line bg-surface py-2 shadow-pop">
                    <div className="border-b border-line px-4 pb-3 pt-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-ink">{user.name}</span>
                        <span className="rounded-full bg-primary-soft px-2 py-0.5 text-[11px] text-primary">
                          {ROLE_LABEL[user.role]}
                        </span>
                        {user.isAdmin && (
                          <span className="rounded-full bg-danger-soft px-2 py-0.5 text-[11px] text-danger">
                            管理员
                          </span>
                        )}
                      </div>
                      <div className="mt-1 truncate text-xs text-ink2">{user.email ?? user.id}</div>
                    </div>

                    <Link
                      to="/me"
                      onClick={() => setMenuOpen(false)}
                      className="flex items-center gap-2 px-4 py-2.5 text-sm text-ink hover:bg-page"
                    >
                      <UserRound size={16} /> 个人中心
                    </Link>

                    {/* 管理员入口与基础身份入口视觉分离（SRS 2.3） */}
                    {user.isAdmin && (
                      <div className="mt-1 border-t border-line pt-1">
                        <Link
                          to="/admin"
                          onClick={() => setMenuOpen(false)}
                          className="flex items-center gap-2 px-4 py-2.5 text-sm text-danger hover:bg-danger-soft"
                        >
                          <ShieldAlert size={16} /> 内容治理后台
                        </Link>
                      </div>
                    )}

                    <div className="mt-1 border-t border-line pt-1">
                      <button
                        onClick={handleLogout}
                        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-ink2 hover:bg-page hover:text-ink"
                      >
                        <LogOut size={16} /> 退出登录
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          ) : (
            <Link
              to="/login"
              className="inline-flex h-9 items-center rounded-full border border-line bg-surface px-5 text-sm font-medium text-ink transition-colors hover:border-primary/40 hover:text-primary"
            >
              登录
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
