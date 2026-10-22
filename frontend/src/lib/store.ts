// Zustand auth store: token localStorage'da, kullanıcı bilgisi global state'te.

import { create } from "zustand";

import { api, getToken, type UserInfo } from "./api";

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: true,
  error: null,

  async login(username, password) {
    set({ loading: true, error: null });
    try {
      await api.login(username, password);
      const user = await api.me();
      set({ user, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
      throw e;
    }
  },

  logout() {
    api.logout();
    set({ user: null, loading: false });
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
  },

  async checkAuth() {
    const token = getToken();
    if (!token) {
      set({ loading: false });
      return;
    }
    try {
      const user = await api.me();
      set({ user, loading: false });
    } catch {
      api.logout();
      set({ user: null, loading: false });
    }
  },
}));
