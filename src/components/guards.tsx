import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/features/useAuth';
import { PageLoader } from '@/components/ui/Feedback';

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) return <PageLoader text="正在恢复会话…" />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return <>{children}</>;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && !user.isAdmin) return <Navigate to="/403" replace />;
  return <>{children}</>;
}

export function RequireStudent({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && user.role !== 'student') return <Navigate to="/403" replace />;
  return <>{children}</>;
}
