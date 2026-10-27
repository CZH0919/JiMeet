import { Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { AppHeader } from '@/components/layout/AppHeader';
import { ToastHost } from '@/components/ui/ToastHost';
import { RequireAdmin, RequireAuth } from '@/components/guards';
import { LoginPage } from '@/pages/LoginPage';
import { HomePage } from '@/pages/HomePage';
import { JobsPage } from '@/pages/JobsPage';
import { JobDetailPage } from '@/pages/JobDetailPage';
import { JobFormPage } from '@/pages/JobFormPage';
import { JobApplicationsPage } from '@/pages/JobApplicationsPage';
import { ProfilePage } from '@/pages/ProfilePage';
import { NotificationsPage } from '@/pages/NotificationsPage';
import { AdminPage } from '@/pages/AdminPage';
import { ChatPage } from '@/pages/ChatPage';
import { ForbiddenPage, NotFoundPage } from '@/pages/ErrorPages';

function AppLayout() {
  return (
    <div className="min-h-screen">
      <AppHeader />
      <main>
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
        <Route path="/" element={<HomePage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/new" element={<RequireAuth><JobFormPage /></RequireAuth>} />
        <Route path="/jobs/:id" element={<JobDetailPage />} />
        <Route path="/jobs/:id/edit" element={<RequireAuth><JobFormPage /></RequireAuth>} />
        <Route path="/jobs/:id/applications" element={<RequireAuth><JobApplicationsPage /></RequireAuth>} />
        <Route path="/me" element={<RequireAuth><ProfilePage /></RequireAuth>} />
        <Route path="/me/applications" element={<Navigate to="/me" replace />} />
        <Route path="/messages" element={<RequireAuth><ChatPage /></RequireAuth>} />
        <Route path="/notifications" element={<RequireAuth><NotificationsPage /></RequireAuth>} />
        <Route path="/admin" element={<RequireAuth><RequireAdmin><AdminPage /></RequireAdmin></RequireAuth>} />
        <Route path="/403" element={<ForbiddenPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
