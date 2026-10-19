const API_BASE = import.meta.env.VITE_API_URL || '';

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface BoundingRegion {
  x: number;
  y: number;
  w: number;
  h: number;
  corridor_id?: string;
  drift_velocity?: string;
  tracking_status?: string;
  persistence_frames?: number;
  offshore_distance_m?: number;
  gps_coordinates?: { lat: number; lon: number } | null;
}


export interface Detection {
  id: string;
  start_timestamp_sec: number;
  end_timestamp_sec: number;
  confidence: number;
  bounding_region: BoundingRegion | null;
}

export interface TimelinePoint {
  t: number;
  confidence: number;
  region?: BoundingRegion | null;
}

export type FeedbackType =
  | 'confirmed_true_positive'
  | 'false_positive_wake'
  | 'false_positive_sandbar'
  | 'false_positive_wave_break'
  | 'false_positive_other'
  | 'missed_detection';

export interface DetectionFeedback {
  id: string;
  session_id: string;
  detection_id: string | null;
  user_id: string;
  feedback_type: FeedbackType;
  confidence_rating: number | null;
  operator_notes: string | null;
  corrected_region: any | null;
  created_at: string;
}

export interface FeedbackPayload {
  detection_id?: string | null;
  feedback_type: FeedbackType;
  confidence_rating?: number | null;
  operator_notes?: string | null;
  corrected_region?: any | null;
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
  feedback?: DetectionFeedback[];
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
  const token = getAuthToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${API_BASE}/api/sessions/${sessionId}/video${query}`;
}

export function getLiveFeedUrl(sessionId: string): string {
  const token = getAuthToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${API_BASE}/api/sessions/${sessionId}/live-feed${query}`;
}

export function getStreamFeedUrl(source?: string): string {
  const token = getAuthToken();
  const params = new URLSearchParams();
  if (source) params.set('source', source);
  if (token) params.set('token', token);
  const q = params.toString();
  return `${API_BASE}/api/stream/feed${q ? `?${q}` : ''}`;
}

export async function submitSessionFeedback(
  sessionId: string,
  payload: FeedbackPayload,
): Promise<DetectionFeedback> {
  return apiFetch(`/api/sessions/${sessionId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function getSessionFeedback(sessionId: string): Promise<DetectionFeedback[]> {
  return apiFetch(`/api/sessions/${sessionId}/feedback`);
}

export async function getActiveLearningManifest(sessionId: string): Promise<any> {
  return apiFetch(`/api/sessions/${sessionId}/active-learning-manifest`);
}

export async function getStreamCalibration(source?: string): Promise<any> {
  const q = source ? `?source=${encodeURIComponent(source)}` : '';
  return apiFetch(`/api/stream/calibration${q}`);
}

export async function calibrateStreamCamera(payload: any): Promise<any> {
  return apiFetch('/api/stream/calibration', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function projectStreamCoordinate(payload: any): Promise<any> {
  return apiFetch('/api/stream/calibration/project', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function getHardwareEdgeStatus(): Promise<any> {
  return apiFetch('/api/stream/hardware');
}



