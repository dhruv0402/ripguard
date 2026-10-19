import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  getAuthToken,
  setAuthToken,
  removeAuthToken,
  getVideoUrl,
  getLiveFeedUrl,
  getStreamFeedUrl,
  apiFetch,
} from './api';

const storageMap = new Map<string, string>();
const localStorageMock = {
  getItem: (key: string) => storageMap.get(key) ?? null,
  setItem: (key: string, val: string) => storageMap.set(key, val),
  removeItem: (key: string) => storageMap.delete(key),
  clear: () => storageMap.clear(),
};
vi.stubGlobal('localStorage', localStorageMock);

const eventTarget = new EventTarget();
vi.stubGlobal('window', eventTarget);
vi.stubGlobal('Event', Event);


describe('Frontend API Module', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.restoreAllMocks();
  });


  it('manages auth tokens in localStorage correctly', () => {
    expect(getAuthToken()).toBeNull();

    setAuthToken('test-jwt-token-123');
    expect(getAuthToken()).toBe('test-jwt-token-123');

    removeAuthToken();
    expect(getAuthToken()).toBeNull();
  });

  it('generates authenticated URLs with token query parameters', () => {
    setAuthToken('abc.jwt.token');

    const videoUrl = getVideoUrl('session-xyz');
    expect(videoUrl).toContain('/api/sessions/session-xyz/video?token=abc.jwt.token');

    const liveFeedUrl = getLiveFeedUrl('session-xyz');
    expect(liveFeedUrl).toContain('/api/sessions/session-xyz/live-feed?token=abc.jwt.token');

    const streamUrl = getStreamFeedUrl('test_assets/beach.mp4');
    expect(streamUrl).toContain('/api/stream/feed?');
    expect(streamUrl).toContain('source=test_assets%2Fbeach.mp4');
    expect(streamUrl).toContain('token=abc.jwt.token');
  });

  it('generates clean URLs when no token is present', () => {
    removeAuthToken();

    const videoUrl = getVideoUrl('session-xyz');
    expect(videoUrl).toBe('/api/sessions/session-xyz/video');

    const liveFeedUrl = getLiveFeedUrl('session-xyz');
    expect(liveFeedUrl).toBe('/api/sessions/session-xyz/live-feed');

    const streamUrl = getStreamFeedUrl('test_assets/beach.mp4');
    expect(streamUrl).toBe('/api/stream/feed?source=test_assets%2Fbeach.mp4');
  });

  it('injects Authorization header in apiFetch when token exists', async () => {
    setAuthToken('my-secret-token');

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });
    vi.stubGlobal('fetch', mockFetch);

    const data = await apiFetch('/api/sessions');
    expect(data).toEqual({ status: 'ok' });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, options] = mockFetch.mock.calls[0];
    const headers = options.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer my-secret-token');
  });

  it('clears token and dispatches auth error event on HTTP 401', async () => {
    setAuthToken('expired-token');

    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Token expired' }),
    });
    vi.stubGlobal('fetch', mockFetch);

    const eventSpy = vi.fn();
    window.addEventListener('ripguard_auth_error', eventSpy);

    await expect(apiFetch('/api/sessions')).rejects.toThrow('Token expired');
    expect(getAuthToken()).toBeNull();
    expect(eventSpy).toHaveBeenCalledTimes(1);

    window.removeEventListener('ripguard_auth_error', eventSpy);
  });

  it('submits operator feedback and requests active learning manifest', async () => {
    setAuthToken('op-token');
    const mockFetch = vi.fn().mockImplementation(async (url: string, opts?: any) => {
      if (url.includes('/feedback') && opts?.method === 'POST') {
        return {
          ok: true,
          json: async () => ({ id: 'fb-1', feedback_type: 'confirmed_true_positive' }),
        };
      }
      if (url.includes('/active-learning-manifest')) {
        return {
          ok: true,
          json: async () => ({ summary: { total_hard_negatives: 0, total_confirmed_positives: 1 } }),
        };
      }
      return { ok: true, json: async () => [] };
    });
    vi.stubGlobal('fetch', mockFetch);

    const { submitSessionFeedback, getActiveLearningManifest } = await import('./api');
    const fb = await submitSessionFeedback('sess-1', {
      feedback_type: 'confirmed_true_positive',
      operator_notes: 'Confirmed strong channel',
    });
    expect(fb.feedback_type).toBe('confirmed_true_positive');

    const manifest = await getActiveLearningManifest('sess-1');
    expect(manifest.summary.total_confirmed_positives).toBe(1);
  });
});

