const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface Detection {
  id: string;
  start_timestamp_sec: number;
  end_timestamp_sec: number;
  confidence: number;
  bounding_region: { x: number; y: number; w: number; h: number } | null;
}

export interface TimelinePoint {
  t: number;
  confidence: number;
}

export interface AnalysisSession {
  id: string;
  filename: string;
  location_label: string | null;
  storage_path: string;
  annotated_video_path: string | null;
  status: 'pending' | 'processing' | 'done' | 'failed';
  error_message: string | null;
  overall_risk_level: 'low' | 'medium' | 'high' | null;
  risk_timeline: TimelinePoint[] | null;
  created_at: string;
  detections?: Detection[];
}

export interface BenchmarkRun {
  id?: string;
  model_version: string;
  dataset_split: string;
  iou: number;
  dice_f1: number;
  precision: number;
  recall: number;
  notes: string | null;
  run_at: string;
}

export function getAuthToken(): string | null {
  return localStorage.getItem('ripguard_token');
}

export function setAuthToken(token: string): void {
  localStorage.setItem('ripguard_token', token);
}

export function removeAuthToken(): void {
  localStorage.removeItem('ripguard_token');
}

export async function apiFetch(endpoint: string, options: RequestInit = {}) {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401) {
      removeAuthToken();
      window.dispatchEvent(new Event('ripguard_auth_error'));
    }
    const errorBody = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(errorBody.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export function getVideoUrl(sessionId: string): string {
  return `${API_BASE}/api/sessions/${sessionId}/video`;
}
