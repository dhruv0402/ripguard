import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from '../api';
import { LiveStreamScreen } from './LiveStreamScreen';
vi.mock('../api', () => ({ getStreamFeedUrl: (source: string) => `/feed?source=${source}`, apiFetch: vi.fn() }));
vi.mock('../components/Navbar', () => ({ DisclaimerBanner: () => null }));
describe('live stream availability', () => {
  it('renders connecting telemetry as unknown rather than safe or live', () => {
    const html = renderToStaticMarkup(<LiveStreamScreen />);
    expect(html).toContain('UNKNOWN');
    expect(html).toContain('Unavailable');
    expect(html).not.toContain('>LOW<');
    expect(html).not.toContain('0.0%');
    expect(html).not.toContain('LIVE FEED');
  });
  it('does not claim measured hardware or calibration results', () => {
    const html = renderToStaticMarkup(<LiveStreamScreen />);
    for (const claim of ['Jetson Orin Ready', 'RTK Certified', '15.2W', '30 FPS Sustained', 'Apple Silicon MPS', 'TCA (α=0.65) Active']) expect(html).not.toContain(claim);
  });
});

// Server rendering does not run polling effects; supply a received telemetry state
// through the state hook to exercise the real component's rendering branches.
const state = vi.hoisted(() => ({ telemetry: null as any, effect: null as any, updates: [] as any[], source: '' }));
vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>();
  return { ...actual,
    useEffect: (effect: any) => { state.effect = effect; },
    useState: (initial: any) => {
      const isTelemetry = initial && typeof initial === 'object' && 'risk_level' in initial;
      const [value, setter] = actual.useState(isTelemetry && state.telemetry ? state.telemetry
        : initial === 'test_assets/beach_ripvis_072.mp4' && state.source ? state.source : initial);
      return [value, (next: any) => { if (isTelemetry) state.updates.push(next); setter(next); }];
    },
  };
});

describe('received telemetry', () => {
  it.each([
    { status: 'degraded', confidence: null, risk_level: 'UNKNOWN', error: 'model_unavailable' },
    { status: 'offline', confidence: 0, risk_level: 'LOW' },
    { status: 'streaming', confidence: null, risk_level: 'UNKNOWN' },
    { status: 'streaming', confidence: NaN, risk_level: 'LOW' },
    { status: 'streaming', confidence: 0.8, risk_level: 'unexpected' },
  ])('does not imply safety for unavailable or invalid data: %j', (telemetry) => {
    state.telemetry = { ...telemetry, fps: 0, timestamp: 0 };
    try {
      const html = renderToStaticMarkup(<LiveStreamScreen />);
      expect(html).toContain('UNKNOWN');
      expect(html).toContain('Unavailable');
      expect(html).not.toContain('>LOW<');
      expect(html).not.toContain('0.0%');
      expect(html).not.toContain('LIVE FEED');
    } finally { state.telemetry = null; }
  });
  it('preserves valid measured zero confidence', () => {
    state.telemetry = { status: 'streaming', confidence: 0, risk_level: 'LOW', fps: 12, timestamp: 0 };
    try {
      const html = renderToStaticMarkup(<LiveStreamScreen />);
      expect(html).toContain('>LOW<');
      expect(html).toContain('0.0%');
    } finally { state.telemetry = null; }
  });
});


describe('telemetry polling lifecycle', () => {
  afterEach(() => { vi.useRealTimers(); vi.mocked(apiFetch).mockReset(); state.source = ''; state.updates = []; });
  it('requests the applied source and clears measurements after a failed request', async () => {
    vi.useFakeTimers();
    state.source = 'rtsp://camera/path?mode=a&b=c';
    vi.mocked(apiFetch).mockRejectedValue(new Error('offline'));
    renderToStaticMarkup(<LiveStreamScreen />);
    const cleanup = state.effect();
    await vi.advanceTimersByTimeAsync(0);
    expect(apiFetch).toHaveBeenCalledWith(`/api/stream/status?source=${encodeURIComponent(state.source)}`, expect.any(Object));
    expect(state.updates[state.updates.length - 1]).toMatchObject({ status: 'offline', confidence: null, risk_level: 'UNKNOWN' });
    cleanup();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('ignores a pending response after source effect cleanup', async () => {
    vi.useFakeTimers();
    let resolve!: (value: any) => void;
    vi.mocked(apiFetch).mockReturnValueOnce(new Promise(done => { resolve = done; }));
    renderToStaticMarkup(<LiveStreamScreen />);
    const cleanup = state.effect();
    cleanup();
    resolve({ status: 'streaming', confidence: 0, risk_level: 'LOW' });
    await vi.advanceTimersByTimeAsync(0);
    expect(state.updates).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
  });
});
