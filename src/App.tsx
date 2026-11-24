import { Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { AppHeader } from '@/components/layout/AppHeader';
import { ToastHost } from '@/components/ui/ToastHost';
import { RequireAdmin, RequireAuth } from '@/components/guards';
import { LoginPage } from '@/pages/LoginPage';
import { HomePage } from '@/pages/HomePage';
import { AnnouncementDetailPage } from '@/pages/AnnouncementDetailPage';
import { AnnouncementFormPage } from '@/pages/AnnouncementFormPage';
import { JobsPage } from '@/pages/JobsPage';
import { JobDetailPage } from '@/pages/JobDetailPage';
import { JobFormPage } from '@/pages/JobFormPage';
import { JobApplicationsPage } from '@/pages/JobApplicationsPage';
import { ProfilePage } from '@/pages/ProfilePage';
import { AdminPage } from '@/pages/AdminPage';
import { ChatPage } from '@/pages/ChatPage';
import { ForbiddenPage, NotFoundPage } from '@/pages/ErrorPages';

function AppLayout() {
  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader />
      <main className="flex-1">
        <Outlet />
      </main>
      <ToastHost />
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<AppLayout />}>
        {/* 首页 = 通知公告 */}
        <Route path="/" element={<HomePage />} />
        <Route path="/announcements/:id" element={<RequireAuth><AnnouncementDetailPage /></RequireAuth>} />
        <Route path="/announcements/new" element={<RequireAuth><RequireAdmin><AnnouncementFormPage /></RequireAdmin></RequireAuth>} />
        <Route path="/announcements/:id/edit" element={<RequireAuth><RequireAdmin><AnnouncementFormPage /></RequireAdmin></RequireAuth>} />

        {/* 招聘 */}
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/new" element={<RequireAuth><JobFormPage /></RequireAuth>} />
        <Route path="/jobs/:id" element={<JobDetailPage />} />
        <Route path="/jobs/:id/edit" element={<RequireAuth><JobFormPage /></RequireAuth>} />
        <Route path="/jobs/:id/applications" element={<RequireAuth><JobApplicationsPage /></RequireAuth>} />

        {/* 个人中心 / 消息 / 治理后台 */}
        <Route path="/me" element={<RequireAuth><ProfilePage /></RequireAuth>} />
        <Route path="/messages" element={<RequireAuth><ChatPage /></RequireAuth>} />
        <Route path="/admin" element={<RequireAuth><RequireAdmin><AdminPage /></RequireAdmin></RequireAuth>} />

        {/* 站内通知已改为页头小喇叭，旧链接回首页 */}
        <Route path="/notifications" element={<Navigate to="/" replace />} />

        <Route path="/403" element={<ForbiddenPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
