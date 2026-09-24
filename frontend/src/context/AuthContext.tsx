import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { User } from '../types';
import { authService } from '../services/auth';
import { setAccessToken, setLogoutHandler } from '../services/api';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (data: { email: string; password: string }) => Promise<void>;
  register: (data: { email: string; password: string; full_name?: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const handleLogoutCleanup = useCallback(() => {
    setUser(null);
    setAccessToken(null);
    localStorage.removeItem('refresh_token');
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      const profile = await authService.getCurrentUser();
      setUser(profile);
    } catch {
      handleLogoutCleanup();
    }
  }, [handleLogoutCleanup]);

  // Initial session rehydration on app mount
  useEffect(() => {
    setLogoutHandler(handleLogoutCleanup);

    const initAuth = async () => {
      const storedRefreshToken = localStorage.getItem('refresh_token');
      if (storedRefreshToken) {
        try {
          await authService.refresh(storedRefreshToken);
          const profile = await authService.getCurrentUser();
          setUser(profile);
        } catch {
          handleLogoutCleanup();
        }
      }
      setIsLoading(false);
    };

    initAuth();
  }, [handleLogoutCleanup]);

  const login = async (data: { email: string; password: string }) => {
    await authService.login(data);
    const profile = await authService.getCurrentUser();
    setUser(profile);
  };

  const register = async (data: { email: string; password: string; full_name?: string }) => {
    await authService.register(data);
    // After registration, log the user in
    await login({ email: data.email, password: data.password });
  };

  const logout = async () => {
    try {
      await authService.logout();
    } finally {
      handleLogoutCleanup();
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
