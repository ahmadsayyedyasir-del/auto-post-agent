import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setAccessToken, getAccessToken, setLogoutHandler } from '../src/services/api';

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>();
  const mockAxiosInstance = {
    defaults: { baseURL: '/api/v1', headers: {} },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  };
  return {
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => mockAxiosInstance),
      post: vi.fn(),
    },
  };
});

describe('API Client & Token Interceptor', () => {
  beforeEach(() => {
    setAccessToken(null);
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('manages in-memory access token without persisting to localStorage', () => {
    expect(getAccessToken()).toBeNull();
    setAccessToken('test-access-token-123');
    expect(getAccessToken()).toBe('test-access-token-123');
    expect(localStorage.getItem('access_token')).toBeNull();
  });

  it('allows setting logout handler', () => {
    const logoutMock = vi.fn();
    setLogoutHandler(logoutMock);
    expect(logoutMock).not.toHaveBeenCalled();
  });
});
