import { apiClient, setAccessToken } from './api';
import {
  AccessTokenResponse,
  MessageResponse,
  TokenResponse,
  User,
} from '../types';

export const authService = {
  async register(data: { email: string; password: string; full_name?: string }): Promise<User> {
    const response = await apiClient.post<User>('/auth/register', data);
    return response.data;
  },

  async login(data: { email: string; password: string }): Promise<TokenResponse> {
    const response = await apiClient.post<TokenResponse>('/auth/login', data);
    setAccessToken(response.data.access_token);
    localStorage.setItem('refresh_token', response.data.refresh_token);
    return response.data;
  },

  async refresh(refreshToken: string): Promise<AccessTokenResponse> {
    const response = await apiClient.post<AccessTokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    setAccessToken(response.data.access_token);
    return response.data;
  },

  async logout(): Promise<MessageResponse> {
    const refreshToken = localStorage.getItem('refresh_token');
    let res: MessageResponse = { message: 'Logged out successfully' };
    try {
      if (refreshToken) {
        const response = await apiClient.post<MessageResponse>('/auth/logout', {
          refresh_token: refreshToken,
        });
        res = response.data;
      }
    } finally {
      localStorage.removeItem('refresh_token');
      setAccessToken(null);
    }
    return res;
  },

  async getCurrentUser(): Promise<User> {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  },
};
