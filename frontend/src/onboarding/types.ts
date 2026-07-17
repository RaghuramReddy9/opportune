export type ProviderName = 'local' | 'openai' | 'openrouter' | 'ollama' | 'custom';

export interface ProviderInfo {
  provider: ProviderName;
  base_url: string;
  model: string;
  requires_api_key: boolean;
  has_api_key: boolean;
}

export interface RoleSuggestion {
  title: string;
  confidence: number;
  reason: string;
}

export interface ResumeProject {
  name: string;
  evidence?: string;
}

export interface ResumeAnalysis {
  name: string;
  headline: string;
  summary: string;
  roles: string[];
  suggested_roles: RoleSuggestion[];
  skills: string[];
  projects: ResumeProject[];
  locations: string[];
  experience_level: string;
  years_experience?: number | null;
  work_modes: string[];
  visa_needed?: boolean | null;
  missing: string[];
  source: string;
}

export interface QuestionOption {
  value: string;
  label: string;
  description: string;
  confidence?: number;
}

export interface OnboardingQuestion {
  id: 'role_priorities' | 'work_focus' | 'experience_levels' | 'location_preferences' | 'authorization';
  number: number;
  required: boolean;
  kind: 'single' | 'multi' | 'location' | 'authorization';
  title: string;
  helper: string;
  options?: QuestionOption[];
  max_selections?: number;
  suggested_locations?: string[];
  work_mode_options?: string[];
}

export interface LocationAnswer {
  locations: string[];
  work_modes: string[];
  willing_to_relocate: boolean;
}

export interface AuthorizationAnswer {
  visa_policy: 'none' | 'needs_sponsorship' | 'opt_cpt' | 'custom' | '';
  employment_types: string[];
  exclusions: string[];
  note?: string;
}

export interface OnboardingAnswers {
  role_priorities: string[];
  work_focus: string;
  experience_levels: string[];
  location_preferences: LocationAnswer;
  authorization: AuthorizationAnswer;
}

export interface SearchPlan {
  name?: string;
  roles: string[];
  skills: string[];
  projects: ResumeProject[];
  locations: string[];
  experience_level: string;
  target_levels: string[];
  work_modes: string[];
  willing_to_relocate: boolean;
  visa_policy: string;
  visa_needed: boolean;
  work_focus: string;
  employment_types: string[];
  exclusions: string[];
  authorization_note?: string;
  timeline: { max_age_days: number };
}

export interface OnboardingSession {
  session_id: string;
  status: 'questions' | 'review' | 'approved';
  filename: string;
  provider: string;
  analysis: ResumeAnalysis;
  questions: OnboardingQuestion[];
  answers: Partial<OnboardingAnswers>;
  final_config: SearchPlan | Record<string, never>;
  profile_id?: string;
  created_at: string;
  updated_at: string;
}

export interface OnboardingStatus {
  needs_onboarding: boolean;
  active_profile_id?: string | null;
  session?: OnboardingSession | null;
  provider: ProviderInfo;
}

export interface ProviderUpdate {
  provider: ProviderName;
  model?: string;
  base_url?: string;
  api_key?: string;
  requires_api_key?: boolean;
}
