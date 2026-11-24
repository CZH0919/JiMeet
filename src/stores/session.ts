import { create } from 'zustand';
import type { User } from '@/domain/models';

interface SessionState {
  user: User | null;
  /** 是否已尝试恢复会话（路由守卫据此决定是否跳转登录） */
  ready: boolean;
  setUser: (u: User | null) => void;
  setReady: (r: boolean) => void;
}

export const useSession = create<SessionState>((set) => ({
  user: null,
  ready: false,
  setUser: (user) => set({ user }),
  setReady: (ready) => set({ ready }),
}));
