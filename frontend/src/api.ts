import type {
  OnboardingAnswers,
  OnboardingSession,
  OnboardingStatus,
  ProviderInfo,
  ProviderUpdate,
} from './onboarding/types';

const BASE = '/api';

export interface Job {
  id: number;
  job_uid: string;
  company: string;
  title: string;
  location: string;
  apply_url: string;
  source: string;
  ats_type: string;
  resume_match_score: number;
  freshness: string;
  freshness_trust: string;
  action_tag: string;
  target_role_families: string[];
  matched_keywords: string[];
  why_matches: string;
  why_risky: string;
  opt_signal: string;
  best_matching_project: string;
  apply_window_score: number;
  apply_window_label: 'high' | 'medium' | 'low' | string;
  apply_window_reasons: string[];
  apply_window_next_action: string;
  is_demo?: number;
  link_status?: string;
  link_verified_at?: string;
  posted_date?: string;
  freshness_source?: string;
  status: string;
  note: string;
  date_discovered: string;
  date_applied: string;
  date_updated: string;
  first_seen_at?: string;
  last_seen_at?: string;
  content_changed_at?: string;
  listing_state?: 'active' | 'missing' | 'closed' | string;
  score_confidence?: 'high' | 'medium' | 'low' | string;
  description?: string;
  work_mode?: 'remote' | 'hybrid' | 'onsite' | 'unknown' | string;
  experience_level?: 'internship' | 'entry_level' | 'mid_level' | 'senior' | 'leadership' | 'unknown' | string;
  employment_type?: string;
  pool_match_reason?: string;
  profile_id?: string;
  visa_sponsorship?: -1 | 0 | 1 | number;
}

export interface DashboardStats {
  total: number;
  apply_now: number;
  pool: number;
  watch: number;
  known_match: number;
  active_pipeline: number;
  closed: number;
}

export interface ProfileInfo {
  profile_id: string;
  name: string;
  is_active: number;
  created_at: string;
  last_used_at: string;
}


export interface ActiveProfileStats {
  profile_id: string;
  name: string;
  total: number;
  in_pipeline: number;
  applied: number;
  last_scrape: string;
}

export interface DashboardModel {
  stats: DashboardStats;
  buckets: Record<string, Job[]>;
  profile?: ActiveProfileStats;
}

export interface SystemHealth {
  ok: boolean;
  service: string;
  catalog?: { active: number; missing: number; closed: number; total: number };
  latest_scrape?: { started_at?: string; finished_at?: string; status?: string; source_count?: number; listing_count?: number } | null;
  scheduler?: {
    running: boolean;
    state?: Record<string, { next_run_at?: string; status?: string; finished_at?: string } | number>;
    config?: { direct_interval_minutes?: number; board_interval_minutes?: number };
  };
}

export interface QualityReport {
  ok: boolean;
  metrics: { exact_bucket_accuracy: number; apply_precision: number; surface_recall: number; unsafe_false_applies: number; fixture_count: number };
}

export interface ScrapeResult {
  ok: boolean;
  raw_count: number;
  dashboard: DashboardModel;
}


export interface AppConfig {
  app?: { name?: string; mode?: string };
  profile?: {
    candidate?: { name?: string; email?: string; linkedin?: string; github?: string };
    target_roles?: string[];
    target_levels?: string[];
    locations?: string[];
    visa_policy?: string;
    timeline?: { max_age_days?: number };
  };
  sources?: Array<{ name: string; label?: string; enabled: boolean; mode: 'free' | 'paid'; api_key_env?: string | null; description?: string }>;
  storage?: { home?: string; sqlite_file?: string };
  dashboard?: { host?: string; port?: number };
  [key: string]: unknown;
}

async function jsonFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const isForm = typeof FormData !== 'undefined' && opts?.body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: isForm ? opts?.headers : { 'content-type': 'application/json', ...opts?.headers },
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export const api = {
  health: () => jsonFetch<SystemHealth>('/health'),
  quality: () => jsonFetch<QualityReport>('/quality'),
  dashboard: () => jsonFetch<DashboardModel>('/dashboard'),
  config: () => jsonFetch<{ ok: boolean; config: AppConfig }>('/config'),
  saveConfig: (config: AppConfig) => jsonFetch<{ ok: boolean; path: string; config: AppConfig }>('/config', { method: 'POST', body: JSON.stringify({ config }) }),

  onboarding: () => jsonFetch<OnboardingStatus>('/onboarding'),
  onboardingProvider: () => jsonFetch<{ ok: boolean; provider: ProviderInfo }>('/onboarding/provider'),
  saveOnboardingProvider: (provider: ProviderUpdate) => jsonFetch<{ ok: boolean; provider: ProviderInfo }>('/onboarding/provider', { method: 'POST', body: JSON.stringify(provider) }),
  testOnboardingProvider: () => jsonFetch<{ ok: boolean; message: string; model?: string }>('/onboarding/provider/test', { method: 'POST' }),
  analyzeOnboardingResume: (text: string, filename = 'resume.txt') => jsonFetch<OnboardingSession>('/onboarding/analyze', { method: 'POST', body: JSON.stringify({ text, filename }) }),
  uploadOnboardingResume: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return jsonFetch<OnboardingSession>('/onboarding/upload', { method: 'POST', body });
  },
  submitOnboardingAnswers: (sessionId: string, answers: OnboardingAnswers) => jsonFetch<OnboardingSession>(`/onboarding/${encodeURIComponent(sessionId)}/answers`, { method: 'POST', body: JSON.stringify({ answers }) }),
  approveOnboarding: (sessionId: string) => jsonFetch<OnboardingSession>(`/onboarding/${encodeURIComponent(sessionId)}/approve`, { method: 'POST' }),
  listProfiles: () => jsonFetch<{ ok: boolean; profiles: ProfileInfo[] }>('/profiles'),
  activateProfile: (profileId: string) => jsonFetch<{ ok: boolean; profile_id: string }>(`/profiles/${encodeURIComponent(profileId)}/activate`, { method: 'POST' }),
  demo: (clearFirst = false) => jsonFetch<{ ok: boolean; inserted: number; dashboard: DashboardModel }>(`/demo?clear_first=${clearFirst}`, { method: 'POST' }),
  exportData: () => jsonFetch<{ ok: boolean; path: string }>('/privacy/export', { method: 'POST' }),
  backupData: () => jsonFetch<{ ok: boolean; path: string }>('/privacy/backup', { method: 'POST' }),
  wipeData: (confirm: string) => jsonFetch<{ ok: boolean; message: string }>('/privacy/wipe', { method: 'POST', body: JSON.stringify({ confirm }) }),

  setStatus: (uid: string, status: string, note?: string) =>
    jsonFetch<{ ok: boolean }>(`/jobs/${encodeURIComponent(uid)}/status`, {
      method: 'POST',
      body: JSON.stringify({ status, note }),
    }),

  scrape: (dryRun = true) =>
    jsonFetch<ScrapeResult>(`/scrape?dry_run=${dryRun}`, { method: 'POST' }),

};
