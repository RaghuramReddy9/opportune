import { useMemo, useRef, useState } from 'react';
import './onboarding.css';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Bot,
  BrainCircuit,
  BriefcaseBusiness,
  Check,
  CheckCircle2,
  ChevronRight,
  Cloud,
  Cpu,
  Eye,
  EyeOff,
  FileText,
  KeyRound,
  Loader2,
  LockKeyhole,
  MapPin,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from 'lucide-react';

import { api } from '../api';
import { normalizeWorkFocuses, parseLocationDraft, toggleCappedSelection } from './formState';
import type {
  AuthorizationAnswer,
  LocationAnswer,
  OnboardingAnswers,
  OnboardingQuestion,
  OnboardingSession,
  OnboardingStatus,
  ProviderInfo,
  ProviderName,
  ProviderUpdate,
  SearchPlan,
} from './types';

type Stage = 'welcome' | 'provider' | 'resume' | 'analysis' | 'questions' | 'review' | 'approved';

interface Props {
  initialStatus: OnboardingStatus;
  onComplete: () => Promise<void>;
}

const PROVIDERS: Array<{
  id: ProviderName;
  label: string;
  description: string;
  badge: string;
  icon: typeof Cpu;
}> = [
  { id: 'local', label: 'Private local analysis', description: 'No account and no internet connection needed.', badge: 'Private · free', icon: Cpu },
  { id: 'openai', label: 'OpenAI', description: 'Use your own OpenAI API key and a supported model.', badge: 'Bring your key', icon: Sparkles },
  { id: 'openrouter', label: 'OpenRouter', description: 'Choose from OpenRouter models with your own key.', badge: 'Many models', icon: Cloud },
  { id: 'ollama', label: 'Ollama', description: 'Use a model running locally through Ollama.', badge: 'Local model', icon: Server },
  { id: 'custom', label: 'Custom endpoint', description: 'Connect any OpenAI-compatible API or model server.', badge: 'Advanced', icon: Bot },
];

const PROVIDER_DEFAULTS: Record<ProviderName, { base_url: string; model: string }> = {
  local: { base_url: '', model: 'Built-in local analyzer' },
  openai: { base_url: 'https://api.openai.com/v1', model: 'gpt-4.1-mini' },
  openrouter: { base_url: 'https://openrouter.ai/api/v1', model: '' },
  ollama: { base_url: 'http://127.0.0.1:11434/v1', model: 'llama3.2' },
  custom: { base_url: '', model: '' },
};

const EMPTY_LOCATION: LocationAnswer = {
  locations: [],
  work_modes: [],
  willing_to_relocate: false,
};

const EMPTY_AUTHORIZATION: AuthorizationAnswer = {
  visa_policy: '',
  employment_types: ['full_time'],
  exclusions: [],
  note: '',
};

const EMPTY_ANSWERS: OnboardingAnswers = {
  role_priorities: [],
  work_focuses: [],
  experience_levels: [],
  location_preferences: EMPTY_LOCATION,
  authorization: EMPTY_AUTHORIZATION,
};

function stageFromStatus(status: OnboardingStatus): Stage {
  if (status.session?.status === 'review') return 'review';
  if (status.session?.status === 'questions') return 'questions';
  return 'welcome';
}

function cleanError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  const jsonStart = raw.indexOf('{');
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(raw.slice(jsonStart));
      if (parsed.detail) return parsed.detail;
    } catch {
      // Keep the original message when an API response is not JSON.
    }
  }
  return raw.replace(/^\d{3}:\s*/, '');
}

function humanize(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function providerNeedsKey(provider: ProviderName): boolean {
  return provider === 'openai' || provider === 'openrouter';
}

function prefillAnswers(session: OnboardingSession): OnboardingAnswers {
  const saved = session.answers as Partial<OnboardingAnswers>;
  if (Object.keys(saved).length) {
    return {
      ...EMPTY_ANSWERS,
      ...saved,
      work_focuses: normalizeWorkFocuses(saved.work_focuses ?? saved.work_focus),
      location_preferences: { ...EMPTY_LOCATION, ...(saved.location_preferences ?? {}) },
      authorization: { ...EMPTY_AUTHORIZATION, ...(saved.authorization ?? {}) },
    };
  }
  const analysis = session.analysis;
  const suggestedRoles = (analysis.suggested_roles ?? []).slice(0, 2).map((role) => role.title);
  const level = analysis.experience_level === 'mid_level'
    ? ['mid_level']
    : analysis.experience_level === 'senior'
      ? []
      : ['new_grad', 'entry_level', 'junior'];
  return {
    ...EMPTY_ANSWERS,
    role_priorities: suggestedRoles,
    experience_levels: level,
    location_preferences: {
      locations: analysis.locations ?? [],
      work_modes: analysis.work_modes ?? [],
      willing_to_relocate: false,
    },
    authorization: { ...EMPTY_AUTHORIZATION },
  };
}

function ProgressRail({ stage, questionIndex }: { stage: Stage; questionIndex: number }) {
  const milestones = [
    { id: 'provider', label: 'Choose analysis', detail: 'Use private analysis or your own model' },
    { id: 'resume', label: 'Add your resume', detail: 'PDF, DOCX, TXT, or pasted text' },
    { id: 'questions', label: 'Clarify your search', detail: 'Five choices that shape your search' },
    { id: 'review', label: 'Approve the plan', detail: 'Nothing runs before you confirm' },
  ];
  const order: Stage[] = ['welcome', 'provider', 'resume', 'analysis', 'questions', 'review', 'approved'];
  const current = order.indexOf(stage);
  return <aside className="onboarding-rail">
    <div className="onboarding-rail-intro">
      <span>Setup takes about 4 minutes</span>
      <h2>A job search that starts with you.</h2>
      <p>Your resume and answers become one search plan that you review before anything starts.</p>
    </div>
    <div className="onboarding-milestones">
      {milestones.map((item, index) => {
        const milestonePosition = order.indexOf(item.id as Stage);
        const active = item.id === stage || (stage === 'analysis' && item.id === 'resume') || (stage === 'questions' && item.id === 'questions');
        const complete = current > milestonePosition;
        return <div className={`onboarding-milestone ${active ? 'active' : ''} ${complete ? 'complete' : ''}`} key={item.id}>
          <div className="milestone-marker">{complete ? <Check size={14} /> : index + 1}</div>
          <div><b>{item.label}</b><span>{item.id === 'questions' && active ? `Question ${questionIndex + 1} of 5` : item.detail}</span></div>
        </div>;
      })}
    </div>
    <div className="onboarding-trust-card">
      <ShieldCheck size={17} />
      <div><b>You stay in control</b><span>We create a draft. Job discovery starts only after you approve it.</span></div>
    </div>
  </aside>;
}

function ProviderStep({
  provider,
  setProvider,
  onBack,
  onContinue,
  busy,
  error,
}: {
  provider: ProviderUpdate;
  setProvider: (next: ProviderUpdate) => void;
  onBack: () => void;
  onContinue: () => void;
  busy: boolean;
  error: string;
}) {
  const [showKey, setShowKey] = useState(false);
  const [connection, setConnection] = useState('');

  async function testConnection() {
    setConnection('Testing connection…');
    try {
      await api.saveOnboardingProvider(provider);
      const result = await api.testOnboardingProvider();
      setConnection(result.message);
    } catch (err) {
      setConnection(cleanError(err));
    }
  }

  function choose(id: ProviderName) {
    setConnection('');
    setProvider({
      provider: id,
      ...PROVIDER_DEFAULTS[id],
      api_key: '',
      requires_api_key: providerNeedsKey(id),
    });
  }

  return <div className="onboarding-step provider-step">
    <div className="onboarding-step-heading">
      <span className="onboarding-kicker"><BrainCircuit size={15} /> Resume analysis</span>
      <h1>Choose how Opportune reads your resume.</h1>
      <p>This choice only affects resume analysis. You will approve your search before any jobs are found.</p>
    </div>
    <div className="provider-grid">
      {PROVIDERS.map((item) => {
        const Icon = item.icon;
        return <button type="button" className={`provider-choice ${provider.provider === item.id ? 'selected' : ''}`} onClick={() => choose(item.id)} key={item.id}>
          <div className="provider-choice-top"><span className="provider-icon"><Icon size={18} /></span><em>{item.badge}</em></div>
          <b>{item.label}</b><span>{item.description}</span>
          <div className="provider-radio">{provider.provider === item.id && <Check size={13} />}</div>
        </button>;
      })}
    </div>
    {provider.provider !== 'local' && <div className="provider-config-card">
      <div className="provider-config-title"><KeyRound size={16} /><div><b>Connection details</b><span>Saved only on this device.</span></div></div>
      <div className="onboarding-field-grid">
        {(provider.provider === 'custom' || provider.provider === 'ollama') && <label>OpenAI-compatible base URL<input value={provider.base_url ?? ''} onChange={(event) => setProvider({ ...provider, base_url: event.target.value })} placeholder="http://127.0.0.1:11434/v1" /></label>}
        <label>Model name<input value={provider.model ?? ''} onChange={(event) => setProvider({ ...provider, model: event.target.value })} placeholder={provider.provider === 'openrouter' ? 'Example: openai/gpt-4.1-mini' : 'Model name'} /></label>
        {provider.provider !== 'ollama' && <label>API key <span className="field-optional">{provider.provider === 'custom' ? 'if required' : 'required'}</span><div className="secret-input"><input type={showKey ? 'text' : 'password'} value={provider.api_key ?? ''} onChange={(event) => setProvider({ ...provider, api_key: event.target.value })} placeholder="Paste your API key" /><button type="button" onClick={() => setShowKey(!showKey)} aria-label={showKey ? 'Hide API key' : 'Show API key'}>{showKey ? <EyeOff size={15} /> : <Eye size={15} />}</button></div></label>}
      </div>
      <div className="provider-test-row"><button className="onboarding-text-button" type="button" onClick={testConnection}>Test connection</button>{connection && <span>{connection}</span>}</div>
    </div>}
    <div className="onboarding-privacy-note"><LockKeyhole size={16} /><p>{provider.provider === 'local' || provider.provider === 'ollama' ? <><b>Your resume stays on this machine.</b> No resume text is sent to an external service with this option.</> : <><b>Your chosen model will receive sanitized career text.</b> Opportune removes common email, phone, and street-address patterns before the request. Review your provider’s data policy.</>}</p></div>
    {error && <div className="onboarding-error"><AlertCircle size={16} /> {error}</div>}
    <div className="onboarding-actions"><button className="onboarding-back" type="button" onClick={onBack}><ArrowLeft size={15} /> Back</button><button className="onboarding-primary" type="button" onClick={onContinue} disabled={busy}>{busy ? <Loader2 className="spin" size={16} /> : null} Save choice and continue <ArrowRight size={15} /></button></div>
  </div>;
}

function ResumeStep({
  provider,
  onBack,
  onAnalyze,
  busy,
  error,
}: {
  provider: ProviderInfo;
  onBack: () => void;
  onAnalyze: (file: File | null, text: string) => void;
  busy: boolean;
  error: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState('');
  const [dragging, setDragging] = useState(false);
  const ready = !!file || text.trim().length >= 20;

  function handleFile(next: File | undefined) {
    if (!next) return;
    setFile(next);
    setText('');
  }

  return <div className="onboarding-step resume-step">
    <div className="onboarding-step-heading">
      <span className="onboarding-kicker"><FileText size={15} /> Your experience</span>
      <h1>Add the resume you want to use for this search.</h1>
      <p>Opportune looks for the skills, projects, and experience already in your resume. You will confirm the direction before anything starts.</p>
    </div>
    <button
      type="button"
      className={`resume-dropzone ${dragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => { event.preventDefault(); setDragging(false); handleFile(event.dataTransfer.files[0]); }}
    >
      <input ref={inputRef} type="file" accept=".pdf,.docx,.txt,.md,.markdown" hidden onChange={(event) => handleFile(event.target.files?.[0])} />
      <span className="resume-upload-icon">{file ? <CheckCircle2 size={25} /> : <UploadCloud size={25} />}</span>
      {file ? <><b>{file.name}</b><span>{Math.max(1, Math.round(file.size / 1024))} KB · ready to analyze</span><em>Choose a different file</em></> : <><b>Drop your resume here</b><span>PDF, DOCX, TXT, or Markdown · up to 5 MB</span><em>Browse files</em></>}
    </button>
    <div className="resume-divider"><span>or paste the text</span></div>
    <label className="resume-paste-label">Resume text<textarea value={text} onChange={(event) => { setText(event.target.value); setFile(null); }} placeholder="Paste the complete resume text here…" /><span>{text.trim().length ? `${text.trim().length.toLocaleString()} characters` : 'Nothing is submitted to employers.'}</span></label>
    <div className="onboarding-privacy-note"><ShieldCheck size={16} /><p>{provider.provider === 'local' || provider.provider === 'ollama' ? <><b>Private analysis selected.</b> Resume processing stays local to this machine.</> : <><b>Contact details are filtered before the model request.</b> Your complete resume remains in local storage for matching after you approve the plan.</>}</p></div>
    {error && <div className="onboarding-error"><AlertCircle size={16} /> {error}</div>}
    <div className="onboarding-actions"><button className="onboarding-back" type="button" onClick={onBack}><ArrowLeft size={15} /> Back</button><button className="onboarding-primary" type="button" onClick={() => onAnalyze(file, text)} disabled={!ready || busy}>{busy ? <Loader2 className="spin" size={16} /> : <BrainCircuit size={16} />} {busy ? 'Reading your resume…' : 'Analyze my resume'} <ArrowRight size={15} /></button></div>
  </div>;
}

function AnalysisStep({ session, onContinue, onBack }: { session: OnboardingSession; onContinue: () => void; onBack: () => void }) {
  const analysis = session.analysis;
  return <div className="onboarding-step analysis-step">
    <div className="onboarding-step-heading">
      <span className="onboarding-kicker"><Sparkles size={15} /> Draft profile</span>
      <h1>Here is what we found in your resume.</h1>
      <p>This is a starting point. Your next five answers decide which direction the search should take.</p>
    </div>
    <div className="analysis-hero-card">
      <div><span>Draft headline</span><h2>{analysis.headline}</h2><p>{analysis.summary}</p></div>
      <div className="analysis-source"><BrainCircuit size={18} /><span>Analyzed with</span><b>{session.provider === 'local' ? 'Built-in local analysis' : session.provider}</b></div>
    </div>
    <section className="analysis-section"><div className="analysis-section-title"><div><span>Possible directions</span><h3>Roles that fit your experience</h3></div><b>{analysis.suggested_roles.length} suggestions</b></div><div className="analysis-role-grid">{analysis.suggested_roles.map((role, index) => <article key={role.title}><div><span>{index + 1}</span><em>{Math.round(role.confidence * 100)}% confidence</em></div><h4>{role.title}</h4><p>{role.reason}</p></article>)}</div></section>
    <div className="analysis-two-column"><section><span className="analysis-label">Skills found</span><div className="analysis-chips">{analysis.skills.slice(0, 18).map((skill) => <span key={skill}>{skill}</span>)}</div></section><section><span className="analysis-label">Project evidence</span><div className="analysis-projects">{analysis.projects.slice(0, 4).map((project) => <div key={project.name}><BriefcaseBusiness size={14} /><p><b>{project.name}</b><span>{project.evidence || 'Project listed in your resume.'}</span></p></div>)}{!analysis.projects.length && <p className="onboarding-muted">No named projects were identified. You can still continue.</p>}</div></section></div>
    {!!analysis.missing.length && <div className="analysis-missing"><AlertCircle size={16} /><div><b>We still need your input</b><span>{analysis.missing.join(' · ')}</span></div></div>}
    <div className="onboarding-actions"><button className="onboarding-back" type="button" onClick={onBack}><ArrowLeft size={15} /> Use another resume</button><button className="onboarding-primary" type="button" onClick={onContinue}>Answer 5 questions <ArrowRight size={15} /></button></div>
  </div>;
}

function ToggleOption({ selected, label, description, onClick, order }: { selected: boolean; label: string; description?: string; onClick: () => void; order?: number }) {
  return <button type="button" className={`question-option ${selected ? 'selected' : ''}`} onClick={onClick}>
    <span className="question-check">{selected ? (order ? order : <Check size={14} />) : null}</span>
    <div><b>{label}</b>{description && <span>{description}</span>}</div>
  </button>;
}

function LocationInput({ locations, onChange }: { locations: string[]; onChange: (locations: string[]) => void }) {
  const [draft, setDraft] = useState(() => locations.join(', '));
  return <label>Countries, cities, or regions<input value={draft} onChange={(event) => {
    const next = event.target.value;
    setDraft(next);
    onChange(parseLocationDraft(next));
  }} placeholder="Example: United States, New York, Remote US" /><span>Separate multiple locations with commas.</span></label>;
}

function QuestionBody({ question, answers, setAnswers }: { question: OnboardingQuestion; answers: OnboardingAnswers; setAnswers: (next: OnboardingAnswers) => void }) {
  if (question.id === 'role_priorities') {
    return <div className="question-options role-question-options">{(question.options ?? []).map((option) => {
      const order = answers.role_priorities.indexOf(option.value) + 1;
      return <ToggleOption key={option.value} selected={order > 0} order={order || undefined} label={option.label} description={option.description} onClick={() => {
        const selected = answers.role_priorities.includes(option.value);
        const roles = selected ? answers.role_priorities.filter((item) => item !== option.value) : answers.role_priorities.length < 3 ? [...answers.role_priorities, option.value] : answers.role_priorities;
        setAnswers({ ...answers, role_priorities: roles });
      }} />;
    })}</div>;
  }
  if (question.id === 'work_focus') {
    return <div className="question-options">{(question.options ?? []).map((option) => {
      const order = answers.work_focuses.indexOf(option.value) + 1;
      return <ToggleOption key={option.value} selected={order > 0} order={order || undefined} label={option.label} description={option.description} onClick={() => setAnswers({
        ...answers,
        work_focuses: toggleCappedSelection(answers.work_focuses, option.value, question.max_selections ?? 3),
      })} />;
    })}</div>;
  }
  if (question.id === 'experience_levels') {
    return <div className="question-options compact-options">{(question.options ?? []).map((option) => <ToggleOption key={option.value} selected={answers.experience_levels.includes(option.value)} label={option.label} description={option.description} onClick={() => {
      const levels = answers.experience_levels.includes(option.value) ? answers.experience_levels.filter((item) => item !== option.value) : [...answers.experience_levels, option.value];
      setAnswers({ ...answers, experience_levels: levels });
    }} />)}</div>;
  }
  if (question.id === 'location_preferences') {
    const location = answers.location_preferences;
    return <div className="location-question">
      <LocationInput locations={location.locations} onChange={(locations) => setAnswers({ ...answers, location_preferences: { ...location, locations } })} />
      <div><span className="question-subhead">Work modes you can accept</span><div className="question-pill-row">{(question.work_mode_options ?? []).map((mode) => <button type="button" className={location.work_modes.includes(mode) ? 'selected' : ''} onClick={() => {
        const modes = location.work_modes.includes(mode) ? location.work_modes.filter((item) => item !== mode) : [...location.work_modes, mode];
        setAnswers({ ...answers, location_preferences: { ...location, work_modes: modes } });
      }} key={mode}>{location.work_modes.includes(mode) && <Check size={13} />}{humanize(mode)}</button>)}</div></div>
      <label className="question-checkbox"><input type="checkbox" checked={location.willing_to_relocate} onChange={(event) => setAnswers({ ...answers, location_preferences: { ...location, willing_to_relocate: event.target.checked } })} /><span><b>I am open to relocating</b><small>This allows location matches beyond your current area.</small></span></label>
    </div>;
  }
  const authorization = answers.authorization;
  return <div className="authorization-question">
    <div className="question-options compact-options">{(question.options ?? []).map((option) => <ToggleOption key={option.value} selected={authorization.visa_policy === option.value} label={option.label} description={option.description} onClick={() => setAnswers({ ...answers, authorization: { ...authorization, visa_policy: option.value as AuthorizationAnswer['visa_policy'] } })} />)}</div>
    <div><span className="question-subhead">Employment types you will consider</span><div className="question-pill-row">{[['full_time', 'Full time'], ['contract', 'Contract'], ['part_time', 'Part time']].map(([value, label]) => <button type="button" className={authorization.employment_types.includes(value) ? 'selected' : ''} onClick={() => {
      const types = authorization.employment_types.includes(value) ? authorization.employment_types.filter((item) => item !== value) : [...authorization.employment_types, value];
      setAnswers({ ...answers, authorization: { ...authorization, employment_types: types } });
    }} key={value}>{authorization.employment_types.includes(value) && <Check size={13} />}{label}</button>)}</div></div>
    <label>Deal-breakers or roles to exclude<textarea value={authorization.exclusions.join('\n')} onChange={(event) => setAnswers({ ...answers, authorization: { ...authorization, exclusions: event.target.value.split('\n').map((item) => item.trim()).filter(Boolean) } })} placeholder={'One per line\nSecurity clearance required\nUnpaid roles'} /></label>
    {authorization.visa_policy === 'custom' && <label>Work authorization note<textarea value={authorization.note ?? ''} onChange={(event) => setAnswers({ ...answers, authorization: { ...authorization, note: event.target.value } })} placeholder="Add only what the search needs to know." /></label>}
  </div>;
}

function questionReady(question: OnboardingQuestion, answers: OnboardingAnswers): boolean {
  if (question.id === 'role_priorities') return answers.role_priorities.length > 0;
  if (question.id === 'work_focus') return answers.work_focuses.length > 0;
  if (question.id === 'experience_levels') return answers.experience_levels.length > 0;
  if (question.id === 'location_preferences') return answers.location_preferences.locations.length > 0 && answers.location_preferences.work_modes.length > 0;
  return !!answers.authorization.visa_policy && answers.authorization.employment_types.length > 0;
}

function QuestionsStep({ session, answers, setAnswers, questionIndex, setQuestionIndex, onReview, busy, error }: { session: OnboardingSession; answers: OnboardingAnswers; setAnswers: (next: OnboardingAnswers) => void; questionIndex: number; setQuestionIndex: (next: number) => void; onReview: () => void; busy: boolean; error: string }) {
  const question = session.questions[questionIndex];
  const ready = questionReady(question, answers);
  return <div className="onboarding-step questions-step">
    <div className="question-progress"><span>Question {questionIndex + 1} of 5</span><div><i style={{ width: `${((questionIndex + 1) / 5) * 100}%` }} /></div><b>{Math.round(((questionIndex + 1) / 5) * 100)}%</b></div>
    <div className="onboarding-step-heading question-heading"><span className="onboarding-kicker">Your decision</span><h1>{question.title}</h1><p>{question.helper}</p></div>
    <QuestionBody question={question} answers={answers} setAnswers={setAnswers} />
    {question.id === 'role_priorities' && <p className="selection-count">{answers.role_priorities.length}/3 roles selected · your selection order sets priority</p>}
    {question.id === 'work_focus' && <p className="selection-count">{answers.work_focuses.length}/3 work types selected · your selection order sets priority</p>}
    {error && <div className="onboarding-error"><AlertCircle size={16} /> {error}</div>}
    <div className="onboarding-actions"><button className="onboarding-back" type="button" onClick={() => setQuestionIndex(Math.max(0, questionIndex - 1))} disabled={questionIndex === 0}><ArrowLeft size={15} /> Previous</button><button className="onboarding-primary" type="button" disabled={!ready || busy} onClick={() => questionIndex < 4 ? setQuestionIndex(questionIndex + 1) : onReview()}>{busy ? <Loader2 className="spin" size={16} /> : null}{questionIndex < 4 ? 'Continue' : 'Build my search plan'} <ArrowRight size={15} /></button></div>
  </div>;
}

function ReviewStep({ plan, onBack, onApprove, busy, error }: { plan: SearchPlan; onBack: () => void; onApprove: () => void; busy: boolean; error: string }) {
  const focusLabels: Record<string, string> = {
    ai_product_engineering: 'AI product engineering',
    model_engineering: 'Model engineering',
    platform_infrastructure: 'Platform and infrastructure',
    customer_facing: 'Customer-facing solutions',
    flexible: 'Broad, evidence-led search',
  };
  return <div className="onboarding-step review-step">
    <div className="onboarding-step-heading">
      <span className="onboarding-kicker"><ShieldCheck size={15} /> Final review</span>
      <h1>Approve the search Opportune will run.</h1>
      <p>These choices decide which jobs Opportune finds and how it orders them. Nothing starts until you approve.</p>
    </div>
    <div className="review-plan-grid">
      <section className="review-plan-card primary"><span>Priority roles</span><h2>{plan.roles.join(' · ')}</h2><p>{(plan.work_focuses ?? [plan.work_focus]).map((focus) => focusLabels[focus] ?? humanize(focus)).join(' · ')}</p></section>
      <section className="review-plan-card"><span>Experience</span><div className="review-token-row">{plan.target_levels.map((item) => <b key={item}>{humanize(item)}</b>)}</div></section>
      <section className="review-plan-card"><span>Location and work mode</span><h3><MapPin size={16} /> {plan.locations.join(' · ')}</h3><div className="review-token-row">{plan.work_modes.map((item) => <b key={item}>{humanize(item)}</b>)}{plan.willing_to_relocate && <b>Open to relocation</b>}</div></section>
      <section className="review-plan-card"><span>Work authorization</span><h3>{plan.visa_policy === 'opt_cpt' ? 'OPT / CPT; future sponsorship may be needed' : humanize(plan.visa_policy)}</h3><p>Employment: {plan.employment_types.map(humanize).join(', ')}</p></section>
      <section className="review-plan-card skills"><span>Skills from your resume</span><div className="review-token-row">{plan.skills.slice(0, 16).map((skill) => <b key={skill}>{skill}</b>)}</div></section>
      <section className="review-plan-card"><span>Search boundaries</span><h3>Listings from the last {plan.timeline.max_age_days} days</h3><p>{plan.exclusions.length ? `Exclude: ${plan.exclusions.join(' · ')}` : 'No additional deal-breakers were added.'}</p></section>
    </div>
    <div className="approval-explainer"><LockKeyhole size={18} /><div><b>When you approve</b><span>This becomes your active search. Opportune will use these roles, levels, locations, and work authorization choices. You can change them later.</span></div></div>
    {error && <div className="onboarding-error"><AlertCircle size={16} /> {error}</div>}
    <div className="onboarding-actions"><button className="onboarding-back" type="button" onClick={onBack}><ArrowLeft size={15} /> Edit answers</button><button className="onboarding-primary approval-button" type="button" onClick={onApprove} disabled={busy}>{busy ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />} Approve and activate my search</button></div>
  </div>;
}

function ApprovedStep({ onComplete }: { onComplete: () => Promise<void> }) {
  const [previewing, setPreviewing] = useState(false);
  const [previewResult, setPreviewResult] = useState<string>('');
  const [error, setError] = useState('');

  async function preview() {
    setPreviewing(true);
    setError('');
    try {
      const result = await api.scrape(true);
      setPreviewResult(`Preview complete: ${result.raw_count} jobs were checked. Nothing was saved.`);
    } catch (err) {
      setError(cleanError(err));
    } finally {
      setPreviewing(false);
    }
  }

  return <div className="onboarding-step approved-step">
    <div className="approved-mark"><Check size={32} /></div>
    <span className="onboarding-kicker">Search ready</span>
    <h1>Your job search now knows what to look for.</h1>
    <p>Your approved profile is active. Your resume helps order the results, and your five choices decide which jobs appear.</p>
    <div className="approved-next-grid"><div><b>1</b><span>Preview your search</span><p>See how many jobs it finds without saving anything.</p></div><div><b>2</b><span>Review each match</span><p>See why a job fits and what you should check.</p></div><div><b>3</b><span>Save results when ready</span><p>Add the jobs you want to your local dashboard.</p></div></div>
    {previewResult && <div className="onboarding-success"><CheckCircle2 size={16} /> {previewResult}</div>}
    {error && <div className="onboarding-error"><AlertCircle size={16} /> {error}</div>}
    <div className="approved-actions"><button className="onboarding-back" type="button" onClick={preview} disabled={previewing}>{previewing ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />} Preview first search</button><button className="onboarding-primary" type="button" onClick={onComplete}>Open my dashboard <ChevronRight size={16} /></button></div>
  </div>;
}

export default function OnboardingWizard({ initialStatus, onComplete }: Props) {
  const [stage, setStage] = useState<Stage>(stageFromStatus(initialStatus));
  const [providerInfo, setProviderInfo] = useState<ProviderInfo>(initialStatus.provider);
  const [provider, setProvider] = useState<ProviderUpdate>({
    provider: initialStatus.provider.provider,
    model: initialStatus.provider.model,
    base_url: initialStatus.provider.base_url,
    api_key: '',
    requires_api_key: initialStatus.provider.requires_api_key,
  });
  const [session, setSession] = useState<OnboardingSession | null>(initialStatus.session ?? null);
  const [answers, setAnswers] = useState<OnboardingAnswers>(() => initialStatus.session ? prefillAnswers(initialStatus.session) : EMPTY_ANSWERS);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const plan = useMemo(() => session?.final_config as SearchPlan | undefined, [session]);

  async function saveProvider() {
    setBusy(true);
    setError('');
    try {
      const result = await api.saveOnboardingProvider(provider);
      setProviderInfo(result.provider);
      setProvider({ ...provider, api_key: '' });
      setStage('resume');
    } catch (err) {
      setError(cleanError(err));
    } finally {
      setBusy(false);
    }
  }

  async function analyze(file: File | null, text: string) {
    setBusy(true);
    setError('');
    try {
      const result = file ? await api.uploadOnboardingResume(file) : await api.analyzeOnboardingResume(text);
      setSession(result);
      setAnswers(prefillAnswers(result));
      setStage('analysis');
    } catch (err) {
      setError(cleanError(err));
    } finally {
      setBusy(false);
    }
  }

  async function buildReview() {
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.submitOnboardingAnswers(session.session_id, answers);
      setSession(result);
      setStage('review');
    } catch (err) {
      setError(cleanError(err));
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.approveOnboarding(session.session_id);
      setSession(result);
      setStage('approved');
    } catch (err) {
      setError(cleanError(err));
    } finally {
      setBusy(false);
    }
  }

  return <div className="onboarding-shell">
    <header className="onboarding-header"><div className="onboarding-brand"><img src="/favicon.svg" alt="" /><b>Opportune</b><span>Set up your search</span></div><div className="onboarding-local"><LockKeyhole size={14} /> Private by default</div></header>
    <div className="onboarding-canvas">
      <ProgressRail stage={stage} questionIndex={questionIndex} />
      <main className="onboarding-main">
        {stage === 'welcome' && <div className="onboarding-step welcome-step">
          <span className="welcome-orbit"><Sparkles size={24} /></span>
          <span className="onboarding-kicker">Welcome to Opportune</span>
          <h1>Build a job search around the work you have actually done.</h1>
          <p className="welcome-lead">Add your resume, clarify five important decisions, and approve the exact search before discovery begins.</p>
          <div className="welcome-promise-grid">
            <div><BrainCircuit size={18} /><b>Evidence first</b><span>Roles and skills need support from your resume.</span></div>
            <div><ShieldCheck size={18} /><b>You approve the plan</b><span>Nothing starts until you approve it.</span></div>
            <div><LockKeyhole size={18} /><b>Your model, your choice</b><span>Use private local analysis or connect your own model.</span></div>
          </div>
          <button className="onboarding-primary welcome-primary" type="button" onClick={() => setStage('provider')}>Set up my search <ArrowRight size={16} /></button>
          <span className="welcome-footnote">Nothing is submitted to employers. You can review and replace your active profile later.</span>
        </div>}
        {stage === 'provider' && <ProviderStep provider={provider} setProvider={setProvider} onBack={() => setStage('welcome')} onContinue={saveProvider} busy={busy} error={error} />}
        {stage === 'resume' && <ResumeStep provider={providerInfo} onBack={() => setStage('provider')} onAnalyze={analyze} busy={busy} error={error} />}
        {stage === 'analysis' && session && <AnalysisStep session={session} onBack={() => setStage('resume')} onContinue={() => { setQuestionIndex(0); setStage('questions'); }} />}
        {stage === 'questions' && session && <QuestionsStep session={session} answers={answers} setAnswers={setAnswers} questionIndex={questionIndex} setQuestionIndex={setQuestionIndex} onReview={buildReview} busy={busy} error={error} />}
        {stage === 'review' && plan && <ReviewStep plan={plan} onBack={() => { setQuestionIndex(4); setStage('questions'); }} onApprove={approve} busy={busy} error={error} />}
        {stage === 'approved' && <ApprovedStep onComplete={onComplete} />}
      </main>
    </div>
  </div>;
}
