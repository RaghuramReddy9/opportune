import { useState, useEffect, useCallback, useRef } from 'react';

import {
  Globe,
  Clock,
  Zap,
  CheckCircle2,
  XCircle,
  Search,
  ExternalLink,
  Check,
  X,
  Eye,
  RotateCcw,
  Settings,
  Sun,
  Moon,
  Activity,
  Hash,

  Database,
  Download,
  ChevronRight,
  ChevronDown,
  ShieldCheck,
  CalendarDays,
  SlidersHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  UserCircle,
  Briefcase,
} from 'lucide-react';
import { api, type Job, type DashboardModel, type AppConfig, type SystemHealth, type QualityReport, type ProfileInfo, type DiscoveryFunnel, type EffectiveSearchRules } from './api';
import OnboardingWizard from './onboarding/OnboardingWizard';
import type { OnboardingStatus } from './onboarding/types';

type BucketKey = 'all' | 'pool' | 'apply_now' | 'watch' | 'known_match' | 'active_pipeline' | 'closed';


const bucketLabels: Record<BucketKey, string> = {
  all: 'All jobs',
  pool: 'Job pool',
  apply_now: 'Apply now',
  watch: 'Watch',
  known_match: 'Known matches',
  active_pipeline: 'Active',
  closed: 'Closed',
};
const bucketOrder: BucketKey[] = ['all', 'pool', 'apply_now', 'watch', 'known_match', 'active_pipeline', 'closed'];

function normalize(text?: string) { return (text ?? '').toLowerCase(); }
function profileDisplayName(name?: string): string | null {
  const value = (name ?? '').trim();
  if (!value || /^(resume|profile|resume\.(txt|md|pdf|docx))$/i.test(value)) return null;
  return value;
}

const sourceCopy: Record<string, { label: string; description: string }> = {
  serpapi_google_jobs: { label: 'Google Jobs via SerpApi', description: 'Search Google Jobs through your SerpApi account.' },
  free_ats_scrape: { label: 'Company career pages', description: 'Check public company career pages directly.' },
  github_lists: { label: 'Curated GitHub job lists', description: 'Check public early-career job lists on GitHub.' },
  jsearch_api: { label: 'JSearch', description: 'Search a broad set of job boards through RapidAPI.' },
  adzuna_api: { label: 'Adzuna', description: 'Search Adzuna listings with your own API account.' },
  builtin_scrape: { label: 'Built In', description: 'Check public Built In listings when permitted.' },
  wellfound_scrape: { label: 'Wellfound', description: 'Off by default because automated access requires permission.' },
  ycombinator_jobs: { label: 'Y Combinator jobs', description: 'Check public startup roles from Y Combinator.' },
};

function sourceLabel(source: SourceConfig): string {
  return source.label || sourceCopy[source.name]?.label || source.name.replace(/_/g, ' ');
}

function sourceDescription(source: SourceConfig): string {
  return sourceCopy[source.name]?.description || source.description || '';
}

function tagLabel(job: Job) {
  if (['applied', 'confirmed', 'interview', 'assessment', 'offer'].includes(job.status)) return job.status;
  if (job.status === 'rejected' || job.status === 'closed') return job.status;
  return job.action_tag.replace(/_/g, ' ');
}
function scoreTone(score: number) {
  if (score >= 90) return 'excellent';
  if (score >= 70) return 'good';
  if (score >= 50) return 'ok';
  return 'low';
}
function windowTone(label?: string) {
  if (label === 'high') return 'high';
  if (label === 'low') return 'low';
  return 'medium';
}
function normalizeReasons(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean);
    } catch { /* fall through */ }
    return value.split(';').map((x) => x.trim()).filter(Boolean);
  }
  return [];
}

function ProfileSwitcher({ profiles, onActivate }: { profiles: ProfileInfo[]; onActivate: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = profiles.find((p) => p.is_active === 1);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (!profiles.length) return null;

  return (
    <div className="profile-switcher" ref={ref}>
      <button type="button" className="profile-pill" onClick={() => setOpen(!open)}>
        <UserCircle size={14} />
        <span>{profileDisplayName(active?.name) || 'Active search'}</span>
        <ChevronDown size={12} className={open ? 'rotated' : ''} />
      </button>
      {open && (
        <div className="profile-dropdown">
          <div className="profile-dropdown-header">Switch profile</div>
          {profiles.map((p) => (
            <button
              key={p.profile_id}
              type="button"
              className={`profile-option ${p.is_active === 1 ? 'active' : ''}`}
              onClick={() => { onActivate(p.profile_id); setOpen(false); }}
            >
              <UserCircle size={13} />
              <span>{profileDisplayName(p.name) || 'Search profile'}</span>
              {p.is_active === 1 && <Check size={12} className="profile-check" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function BucketTabs({ active, counts, onChange }: { active: BucketKey; counts: Record<string, number>; onChange: (bucket: BucketKey) => void }) {
  return <div className="bucket-tabs" role="tablist" aria-label="Dashboard buckets">
    {bucketOrder.map((bucket) => <button key={bucket} type="button" role="tab" aria-selected={active === bucket} className={`bucket-tab ${active === bucket ? 'active' : ''}`} onClick={() => onChange(bucket)}><span>{bucketLabels[bucket]}</span><b>{counts[bucket] ?? 0}</b></button>)}
  </div>;
}

function JobCard({ job, onAction, onSelect }: { job: Job; onAction: (uid: string, action: string) => void; onSelect?: (job: Job) => void }) {
  const [expanded, setExpanded] = useState(false);
  const tone = scoreTone(job.resume_match_score);
  const safeWhy = (job.why_matches || '').replace(/\*\*/g, '');
  const safeRisk = (job.why_risky || '').replace(/\*\*/g, '');
  const source = (job.source || 'source').replace(/^api_/i, '').replace(/_/g, ' ');
  const applyWindow = job.apply_window_label || 'medium';
  const applyWindowText = `${applyWindow} window`.replace(/^./, (c) => c.toUpperCase());
  const applyWindowReasons = normalizeReasons(job.apply_window_reasons);

  const freshnessLabel = job.freshness || 'Unknown';
  const freshnessTrust = job.freshness_trust || 'unverified';
  const freshnessCls = freshnessTrust === 'discovered_not_posted' ? 'freshness-discovered' : freshnessTrust === 'confirmed_posted_date' ? 'freshness-confirmed' : '';

  const linkStatus = job.link_status || '';
  const linkBadge =
    linkStatus === 'ok'
      ? { cls: 'link-ok', text: 'Link verified' }
      : linkStatus === 'placeholder'
        ? { cls: 'link-demo', text: 'Sample link' }
        : linkStatus === 'dead' || linkStatus === 'unreachable'
          ? { cls: 'link-bad', text: 'Link broken' }
          : null;

  return (
    <article className={`job-card ${tone}`}>
      <div className="job-card-glow" />
      <div className="job-header">
        <div className="job-title-block">
        <div className="job-meta-row"><span className={`status-pill ${job.action_tag}`}>{tagLabel(job)}</span><span className={`window-pill ${windowTone(applyWindow)}`}>{applyWindowText} · {job.apply_window_score ?? 0}</span><span className={`muted-pill ${freshnessCls}`}><Clock size={12} /> {freshnessLabel}{job.freshness_source === 'employer_page' ? ' · confirmed' : ''}</span><span className="muted-pill">{(job.work_mode || 'unknown').replace(/_/g, ' ')}</span><span className="muted-pill">{(job.experience_level || 'unknown').replace(/_/g, ' ')}</span><span className="muted-pill"><Globe size={12} /> {source}</span>{linkBadge && <span className={`link-pill ${linkBadge.cls}`}>{linkBadge.text}</span>}{job.is_demo ? <span className="link-pill link-demo">Sample</span> : null}</div>
          <h3>{job.title}</h3>
          <div className="company-line"><strong>{job.company || 'Unknown company'}</strong>{job.location ? <span>{job.location}</span> : <span>Location not listed</span>}</div>
        </div>
        <div className={`score-orb ${tone}`}><span>{job.resume_match_score}</span><small>match</small></div>
      </div>
      {safeWhy && <p className="match-copy">{safeWhy}</p>}
      {safeRisk && <p className="risk-copy">{safeRisk}</p>}
      <div className={`apply-window-box ${windowTone(applyWindow)}`}><b>{job.apply_window_next_action || 'Review before applying'}</b><span>{applyWindowReasons.slice(0, 3).join(' · ') || 'Based on fit, posting date, source, and link quality'}</span></div>
      <div className="keyword-row">
        {(job.matched_keywords ?? []).slice(0, 7).map((kw) => <span key={kw}>+ {kw}</span>)}
        {(job.target_role_families ?? []).slice(0, 3).map((family) => <span className="family" key={family}>{family.replace(/_/g, ' ')}</span>)}
      </div>
      {expanded && <div className="detail-panel"><div className="detail-grid"><div><label>Best project</label><p>{job.best_matching_project || 'No project match saved yet'}</p></div><div><label>Visa signal</label><p>{job.opt_signal || 'Unknown'}</p></div><div><label>Notes</label><p>{job.note || 'No notes yet'}</p></div><div><label>Discovered</label><p>{job.date_discovered || 'Unknown'}</p></div><div><label>Posted date</label><p>{job.posted_date || 'Not available from source'}</p></div></div></div>}
      <div className="card-actions">
        <button type="button" className="ghost-action" onClick={() => onSelect ? onSelect(job) : setExpanded(!expanded)}><Hash size={14} /> Review evidence</button>
        {job.apply_url && !['dead', 'unreachable'].includes(linkStatus) ? <a className="primary-action" href={job.apply_url} target="_blank" rel="noreferrer">Open listing <ExternalLink size={14} /></a> : ['dead', 'unreachable'].includes(linkStatus) ? <span className="disabled-action">Listing unavailable</span> : null}
        <button type="button" className="success-action" onClick={() => onAction(job.job_uid, 'applied')}><Check size={14} /> Mark applied</button>
        <button type="button" className="watch-action" onClick={() => onAction(job.job_uid, 'watch')}><Eye size={14} /> Watch</button>
        <button type="button" className="danger-action" onClick={() => onAction(job.job_uid, 'rejected')}><X size={14} /> Reject</button>
      </div>
    </article>
  );
}

type SourceConfig = NonNullable<AppConfig['sources']>[number];
function sourceReadiness(source: SourceConfig) {
  if (!source.enabled) return { label: 'Disabled', tone: 'off', detail: "Won't run" };
  if (source.name?.toLowerCase().includes('linkedin')) return { label: 'Experimental', tone: 'warn', detail: 'May be rate-limited' };
  if (source.mode === 'paid' && source.api_key_env) return { label: 'Needs key', tone: 'warn', detail: source.api_key_env };
  return { label: 'Ready', tone: 'ready', detail: source.mode === 'free' ? 'No key needed' : 'Configured' };
}

function SettingsPanel({ onLog, onReload }: { onLog: (line: string) => void; onReload: () => Promise<void> }) {
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [wipeConfirm, setWipeConfirm] = useState('');

  const loadConfig = useCallback(async () => {
    const response = await api.config();
    setCfg(response.config);
  }, []);
  useEffect(() => { loadConfig().catch((e) => onLog(`ERROR loading config: ${e}`)); }, [loadConfig, onLog]);

  function updateSource(index: number, patch: Record<string, unknown>) {
    setCfg((current) => {
      const sources = [...(current?.sources ?? [])];
      sources[index] = { ...sources[index], ...patch } as any;
      return { ...(current ?? {}), sources };
    });
  }

  async function saveConfig() {
    if (!cfg) return;
    setBusy(true);
    try {
      await api.saveConfig(cfg);
      onLog('✓ Saved config.yaml');
    } catch (e) { onLog(`ERROR saving config: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setBusy(false); }
  }
  async function loadDemo(clear = false) {
    setBusy(true);
    try {
      const r = await api.demo(clear);
      onLog(`✓ Loaded ${r.inserted} demo jobs`);
      await onReload();
    } catch (e) { onLog(`ERROR demo: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setBusy(false); }
  }
  async function exportOrBackup(kind: 'export' | 'backup') {
    const r = kind === 'export' ? await api.exportData() : await api.backupData();
    onLog(`✓ ${kind}: ${r.path}`);
  }
  async function wipe() {
    setBusy(true);
    try {
      const r = await api.wipeData(wipeConfirm);
      onLog(`✓ ${r.message}`);
      await onReload();
    } catch (e) { onLog(`ERROR wipe: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setBusy(false); }
  }

  if (!cfg) return <div className="empty-state"><RotateCcw className="spin" size={24} /> Loading settings…</div>;

  return (
    <div className="settings-grid">
      <section className="settings-card wide">
        <div className="section-kicker"><Briefcase size={15} /> Your search profile</div>
        <h2>Update what you are looking for.</h2>
        <p>Review your resume, target roles, locations, experience level, and work authorization in one guided flow.</p>
        <button type="button" className="primary-action settings-action" onClick={() => window.location.assign('/onboarding')}>Review search profile</button>
      </section>

      <section className="settings-card wide">
        <div className="section-kicker"><Globe size={15} /> Sources</div>
        <h2>Choose where jobs come from.</h2>
        <p>Free sources work right away. Paid sources stay off until you add their API key.</p>
        <div className="source-list">
          {(cfg.sources ?? []).map((s, i) => {
            const readiness = sourceReadiness(s);
            return <div className="source-row" key={s.name}>
              <div><b>{sourceLabel(s)}</b><span>{sourceDescription(s)}</span></div>
              <span className={`source-badge ${readiness.tone}`}>{readiness.label}<small>{readiness.detail}</small></span>
              <span className="source-mode">{s.mode === 'paid' ? 'Paid source' : 'Free source'}</span>
              <label className="toggle"><input type="checkbox" checked={!!s.enabled} onChange={(e) => updateSource(i, { enabled: e.target.checked })} /> enabled</label>
            </div>;
          })}
        </div>
        <button type="button" className="primary-action settings-action" disabled={busy} onClick={saveConfig}>Save sources</button>
      </section>

      <section className="settings-card accent">
        <div className="section-kicker"><Database size={15} /> Sample and backup</div>
        <h2>Explore without using live jobs.</h2>
        <p>Load sample jobs to try the dashboard. Export or back up your data before clearing it.</p>
        <div className="button-stack"><button className="small-ghost" onClick={() => loadDemo(false)}>Load sample jobs</button><button className="small-ghost" onClick={() => loadDemo(true)}>Replace with sample jobs</button><button className="small-ghost" onClick={() => exportOrBackup('export')}><Download size={14} /> Export JSON</button><button className="small-ghost" onClick={() => exportOrBackup('backup')}>Backup ZIP</button></div>
        <div className="settings-fields"><label>Type WIPE to clear local job data<input value={wipeConfirm} onChange={(e) => setWipeConfirm(e.target.value)} placeholder="WIPE" /></label></div>
        <button type="button" className="danger-action settings-action" disabled={busy || wipeConfirm !== 'WIPE'} onClick={wipe}>Wipe local job data</button>
      </section>
    </div>
  );
}

type WorkspaceView = 'dashboard' | 'discover' | 'review' | 'settings';

function formatMoment(value?: string) {
  if (!value) return 'Not run yet';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(parsed);
}

function jobAgeDays(job: Job): number | null {
  const value = job.posted_date || job.first_seen_at || job.date_discovered;
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return Math.max(0, (Date.now() - parsed.getTime()) / 86_400_000);
}

function matchesApplicationState(job: Job, filter: string): boolean {
  if (filter === 'all') return true;
  const status = job.status || 'discovered';
  if (filter === 'not_applied') return ['discovered', 'watch'].includes(status);
  if (filter === 'active') return ['applied', 'confirmed', 'interview', 'assessment', 'offer'].includes(status);
  if (filter === 'closed') return ['rejected', 'closed'].includes(status);
  return true;
}

function TopMatch({ job, onSelect }: { job: Job; onSelect: (job: Job) => void }) {
  const tone = scoreTone(job.resume_match_score);
  return <button type="button" className={`top-match ${tone}`} onClick={() => onSelect(job)}>
    <div className="top-match-head"><span>{job.location || 'Location unverified'}</span><div className={`mini-score ${tone}`}><b>{job.resume_match_score}%</b><small>match</small></div></div>
    <h3>{job.title}</h3>
    <div className="top-match-skills">{(job.matched_keywords ?? []).slice(0, 4).map((skill) => <span key={skill}>{skill}</span>)}</div>
    <footer><span>{job.company}</span><ChevronRight size={15} /></footer>
  </button>;
}

function ReviewTable({ jobs, onSelect }: { jobs: Job[]; onSelect: (job: Job) => void }) {
  return <div className="review-table-wrap"><table className="review-table"><thead><tr><th>Job</th><th>Match</th><th>Confidence</th><th>Posted</th><th>Source</th><th>Status</th><th /></tr></thead><tbody>
    {jobs.map((job) => <tr key={job.job_uid} onClick={() => onSelect(job)}>
      <td><b>{job.title}</b><span>{job.company} · {job.location || 'Location unverified'}</span></td>
      <td><strong className={`table-score ${scoreTone(job.resume_match_score)}`}>{job.resume_match_score}%</strong></td>
      <td><span className={`evidence-state ${job.score_confidence === 'high' ? 'verified' : ''}`}><ShieldCheck size={13} /> {job.score_confidence === 'high' ? 'Strong' : 'Review'}</span></td>
      <td><span>{job.freshness || 'Unknown'}</span><small>{job.freshness_trust === 'confirmed_posted_date' ? 'Date confirmed' : 'Found date only'}</small></td>
      <td><span className="source-token">{(job.source || 'unknown').replace(/^api_/, '').replace(/_/g, ' ')}</span></td>
      <td><span className={`listing-token ${job.listing_state || 'active'}`}>{job.listing_state || 'active'}</span></td>
      <td><button type="button" aria-label={`Review ${job.title}`}><ChevronRight size={16} /></button></td>
    </tr>)}
  </tbody></table>{!jobs.length && <div className="table-empty">No opportunities match this view.</div>}</div>;
}

function EvidenceDrawer({ job, onClose, onAction }: { job: Job; onClose: () => void; onAction: (uid: string, action: string) => void }) {
  const reasons = normalizeReasons(job.apply_window_reasons);
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();
    const handleKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleKey);
    return () => { window.removeEventListener('keydown', handleKey); previousFocus?.focus(); };
  }, [onClose]);
  return <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className="evidence-drawer" role="dialog" aria-modal="true" aria-label={`Review ${job.title}`}>
    <header><div><span className="drawer-eyebrow">Why this job was suggested</span><h2>{job.title}</h2><p>{job.company} · {job.location || 'Location unverified'}</p></div><button ref={closeButton} type="button" onClick={onClose} aria-label="Close review"><X size={18} /></button></header>
    <div className="drawer-score-row"><div className={`drawer-score ${scoreTone(job.resume_match_score)}`}><b>{job.resume_match_score}%</b><span>resume match</span></div><div><b>Apply timing: {job.apply_window_label || 'medium'}</b><span>{job.apply_window_next_action || 'Review before taking action'}</span></div></div>
    <section><h3>Why it matches</h3><p>{(job.why_matches || 'No explanation stored yet.').replace(/\*\*/g, '')}</p><div className="drawer-skills">{(job.matched_keywords ?? []).map((skill) => <span key={skill}>{skill}</span>)}</div></section>
    <section className="risk-section"><h3>What to check</h3><p>{(job.why_risky || 'Nothing obvious is blocking this match. Check the original listing before applying.').replace(/\*\*/g, '')}</p>{reasons.map((reason) => <div className="reason-line" key={reason}><CheckCircle2 size={14} /> {reason}</div>)}</section>
    <section className="evidence-grid"><div><span>Source</span><b>{job.source || 'Unknown'}</b></div><div><span>Posted</span><b>{job.posted_date || 'Not provided'}</b></div><div><span>Work mode</span><b>{(job.work_mode || 'unknown').replace(/_/g, ' ')}</b></div><div><span>Experience</span><b>{(job.experience_level || 'unknown').replace(/_/g, ' ')}</b></div><div><span>First found</span><b>{formatMoment(job.first_seen_at || job.date_discovered)}</b></div><div><span>Last checked</span><b>{formatMoment(job.last_seen_at || job.date_updated)}</b></div><div><span>Listing status</span><b>{job.listing_state || 'active'}</b></div><div><span>Link status</span><b>{job.link_status || 'not checked'}</b></div></section>
    <footer>{job.apply_url && !['dead', 'unreachable'].includes(job.link_status || '') ? <a className="primary-action" href={job.apply_url} target="_blank" rel="noreferrer">Open original listing <ExternalLink size={14} /></a> : <span className="disabled-action">Original listing unavailable</span>}<button className="success-action" type="button" onClick={() => onAction(job.job_uid, 'applied')}><Check size={14} /> Mark applied</button><button className="danger-action" type="button" onClick={() => onAction(job.job_uid, 'rejected')}><X size={14} /> Dismiss</button></footer>
  </aside></div>;
}

const funnelDiagnosis: Record<string, { title: string; detail: string; action: 'sources' | 'profile' }> = {
  tasks: { title: 'No job sources are enabled.', detail: 'Turn on at least one company-site or job-board source.', action: 'sources' },
  requests: { title: 'Sources could not be reached.', detail: 'Review disabled sources, connection failures, and source health.', action: 'sources' },
  raw: { title: 'Sources returned no listings.', detail: 'Try another source or broaden the approved role and location rules.', action: 'sources' },
  normalized: { title: 'Listings could not be normalized.', detail: 'The source responses did not contain usable listing URLs.', action: 'sources' },
  location: { title: 'Location rules removed every listing.', detail: 'Review the approved locations and remote-work preference.', action: 'profile' },
  acquisition: { title: 'No listing matched the approved search.', detail: 'Review roles and locations; Opportune will not broaden them silently.', action: 'profile' },
  ranking: { title: 'No listing reached ranking.', detail: 'Review the approved role and experience rules.', action: 'profile' },
  freshness: { title: 'Freshness rules removed every listing.', detail: 'Review the maximum listing age in your search profile.', action: 'profile' },
  link: { title: 'No listing has a usable application link.', detail: 'Source links may be missing or need another verification pass.', action: 'sources' },
  persistence: { title: 'No listing was saved.', detail: 'Review local storage health and the preceding funnel stage.', action: 'sources' },
  dashboard: { title: 'Saved listings did not reach the dashboard.', detail: 'Review lifecycle and bucket reasons below.', action: 'profile' },
};

function DiscoveryEmptyState({ funnel, rules, onRun, onSettings }: { funnel: DiscoveryFunnel | null; rules: EffectiveSearchRules | null; onRun: () => void; onSettings: () => void }) {
  const order = ['tasks', 'requests', 'raw', 'normalized', 'location', 'acquisition', 'ranking', 'freshness', 'link', 'lifecycle', 'buckets', 'persistence', 'dashboard'];
  const firstZero = order.find((stage) => funnel?.stages?.[stage]?.count === 0);
  const diagnosis = firstZero ? funnelDiagnosis[firstZero] : null;
  return <div className="diagnostic-empty" role="status">
    <div className="diagnostic-empty-copy"><Activity size={20} /><div><span>{firstZero ? `Discovery stopped at ${firstZero}` : 'No discovery run recorded'}</span><h3>{diagnosis?.title || 'Run discovery to build your local job pool.'}</h3><p>{diagnosis?.detail || 'Opportune will show where listings stop and what to change.'}</p></div></div>
    {rules && <div className="effective-rules"><span><b>Roles</b>{rules.roles.join(', ') || 'Not configured'}</span><span><b>Locations</b>{rules.locations.join(', ') || 'Not configured'}</span><span><b>Freshness</b>{rules.max_age_days} days</span></div>}
    <div className="diagnostic-actions"><button type="button" className="primary-action" onClick={onRun}>Run discovery</button><button type="button" onClick={diagnosis?.action === 'sources' ? onSettings : () => window.location.assign('/onboarding')}>{diagnosis?.action === 'sources' ? 'Review sources' : 'Edit search profile'}</button></div>
  </div>;
}

export default function App() {
  const [dark, setDark] = useState(false);
  const [railOpen, setRailOpen] = useState(true);
  const [view, setView] = useState<WorkspaceView>('dashboard');
  const [data, setData] = useState<DashboardModel | null>(null);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [onboarding, setOnboarding] = useState<OnboardingStatus | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [funnel, setFunnel] = useState<DiscoveryFunnel | null>(null);
  const [effectiveRules, setEffectiveRules] = useState<EffectiveSearchRules | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [scraping, setScraping] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [bucket, setBucket] = useState<BucketKey>('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [minScore, setMinScore] = useState(0);
  const [freshnessFilter, setFreshnessFilter] = useState('all');
  const [workModeFilter, setWorkModeFilter] = useState('all');
  const [experienceFilter, setExperienceFilter] = useState('all');
  const [visaFilter, setVisaFilter] = useState('all');
  const [applicationFilter, setApplicationFilter] = useState('not_applied');
  const [logs, setLogs] = useState<string[]>(['Loading your saved jobs…']);
  const addLog = useCallback((line: string) => setLogs((current) => [...current, line]), []);

  const loadData = useCallback(async () => {
    try {
      const [dashboard, system, ranking, profilesRes, onboardingRes, funnelRes] = await Promise.all([
        api.dashboard(),
        api.health(),
        api.quality(),
        api.listProfiles().catch(() => ({ ok: false, profiles: [] as ProfileInfo[] })),
        api.onboarding(),
        api.discoveryFunnel().catch(() => null),
      ]);
      setData(dashboard);
      setHealth(system);
      setQuality(ranking);
      if (profilesRes && profilesRes.ok) {
        setProfiles(profilesRes.profiles);
      }
      setOnboarding(onboardingRes);
      if (funnelRes) {
        setFunnel('version' in funnelRes.funnel ? funnelRes.funnel as DiscoveryFunnel : null);
        setEffectiveRules(funnelRes.effective_profile);
      }
      setError('');
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { loadData(); const timer = setInterval(loadData, 30000); return () => clearInterval(timer); }, [loadData]);
  useEffect(() => { document.documentElement.classList.toggle('dark', dark); }, [dark]);

  const forceOnboarding = window.location.pathname === '/onboarding'
    || new URLSearchParams(window.location.search).get('onboarding') === '1';

  if (!loading && onboarding && (onboarding.needs_onboarding || forceOnboarding)) {
    return <OnboardingWizard
      initialStatus={onboarding}
      onComplete={async () => {
        window.history.replaceState({}, '', '/');
        await loadData();
      }}
    />;
  }

  const buckets = data?.buckets ?? {};
  const uniqueJobs = Array.from(new Map(Object.values(buckets).flat().map((job) => [job.job_uid, job])).values());
  const counts = { all: uniqueJobs.length, pool: buckets.pool?.length ?? 0, apply_now: buckets.apply_now?.length ?? 0, watch: buckets.watch?.length ?? 0, known_match: buckets.known_match?.length ?? 0, active_pipeline: buckets.active_pipeline?.length ?? 0, closed: buckets.closed?.length ?? 0 };
  const sources = Array.from(new Set(uniqueJobs.map((job) => job.source).filter(Boolean))).sort();
  const effectiveBucket: BucketKey = view === 'review' && bucket === 'all' ? 'watch' : bucket;
  const sourceJobs = effectiveBucket === 'all' ? uniqueJobs : (buckets[effectiveBucket] ?? []);
  const visibleJobs = sourceJobs.filter((job) => {
    const matchesQuery = !query || [job.company, job.title, job.location, job.source, job.description, ...(job.matched_keywords ?? [])].some((part) => normalize(part).includes(normalize(query)));
    const age = jobAgeDays(job);
    const matchesFreshness = freshnessFilter === 'all' || (freshnessFilter === 'unknown' ? age === null : age !== null && age <= Number(freshnessFilter));
    const matchesWorkMode = workModeFilter === 'all' || (job.work_mode || 'unknown') === workModeFilter;
    const matchesExperience = experienceFilter === 'all' || (job.experience_level || 'unknown') === experienceFilter;
    const matchesVisa = visaFilter === 'all' || (visaFilter === 'yes' ? job.visa_sponsorship === 1 : visaFilter === 'no' ? job.visa_sponsorship === 0 : job.visa_sponsorship === -1);
    return matchesQuery && matchesFreshness && matchesWorkMode && matchesExperience && matchesVisa && matchesApplicationState(job, applicationFilter) && (sourceFilter === 'all' || job.source === sourceFilter) && job.resume_match_score >= minScore;
  });
  const rankedJobs = [...uniqueJobs].filter((job) => !['rejected', 'closed'].includes(job.status)).sort((a, b) => b.resume_match_score - a.resume_match_score);
  const topJobs = rankedJobs.slice(0, 4);
  const reviewJobs = rankedJobs.slice(0, 80);
  const nextDirect = (health?.scheduler?.state?.direct as { next_run_at?: string } | undefined)?.next_run_at;
  const nextBoard = (health?.scheduler?.state?.board as { next_run_at?: string } | undefined)?.next_run_at;

  async function runScrape() { setScraping(true); addLog('Looking for new jobs…'); try { const result = await api.scrape(false); setFunnel(result.discovery_funnel); addLog(`Checked ${result.raw_count} jobs`); await loadData(); setView('discover'); } catch (err) { addLog(`ERROR: ${err instanceof Error ? err.message : String(err)}`); } finally { setScraping(false); } }
  async function handleAction(uid: string, action: string) { try { await api.setStatus(uid, action); addLog(`Job marked ${action.replace('_', ' ')}`); setSelectedJob(null); await loadData(); } catch (err) { addLog(`ERROR: ${err instanceof Error ? err.message : String(err)}`); } }
  async function handleActivateProfile(id: string) {
    try {
      await api.activateProfile(id);
      addLog('Profile switched');
      await loadData();
    } catch (err) {
      addLog(`ERROR switching profile: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  const greeting = new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 18 ? 'afternoon' : 'evening';
  const candidateName = profileDisplayName(data?.profile?.name);

  return <div className={`product-shell ${railOpen ? '' : 'rail-collapsed'}`}>
    <header className="global-header">
      <div className="global-brand"><img src="/favicon.svg" alt="" /><b>Opportune</b><span>local</span></div>
      <nav>{(['dashboard', 'discover', 'review'] as WorkspaceView[]).map((item) => <button key={item} type="button" className={view === item ? 'active' : ''} onClick={() => setView(item)}>{item === 'review' ? 'Review queue' : item}</button>)}</nav>
      <div className="global-actions">
        <ProfileSwitcher profiles={profiles} onActivate={handleActivateProfile} />
        <button type="button" className="icon-button" onClick={() => setRailOpen(!railOpen)} aria-label="Toggle guidance rail">{railOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}</button>
        <button type="button" className="icon-button" onClick={() => setDark(!dark)} aria-label="Toggle color mode">{dark ? <Sun size={16} /> : <Moon size={16} />}</button>
        <button type="button" className={view === 'settings' ? 'settings-button active' : 'settings-button'} onClick={() => setView('settings')}><Settings size={15} /> Settings</button>
        <button type="button" className="run-button" disabled={scraping} onClick={runScrape}>{scraping ? <RotateCcw className="spin" size={15} /> : <Zap size={15} />} {scraping ? 'Scanning…' : 'Run discovery'}</button>
      </div>
    </header>
    <aside className="guidance-rail">
      <div>
        <span className="rail-overline">Your feed</span>
        {data?.profile ? (
          <>
            <h2>Your active search</h2>
            <p>Based on your approved profile. {data.profile.total} jobs are saved on this device.</p>
          </>
        ) : (
          <>
            <h2>Ready for your search</h2>
            <p>Set your roles, locations, and preferences before finding jobs.</p>
          </>
        )}
      </div>
      <div className="guidance-card"><Activity size={16} /><div><b>{health?.latest_scrape?.status === 'completed' ? 'Job sources ready' : 'Ready to search'}</b><span>{health?.catalog?.active ?? 0} current · {health?.catalog?.missing ?? 0} no longer listed · {health?.catalog?.closed ?? 0} closed</span></div></div>
      <div className="guidance-card"><CalendarDays size={16} /><div><b>Next refresh</b><span>Company sites: {formatMoment(nextDirect)}<br />Job boards: {formatMoment(nextBoard)}</span></div></div>
      <div className="guidance-card"><ShieldCheck size={16} /><div><b>{quality?.ok ? 'Safety checks passed' : 'Match checks need review'}</b><span>{quality ? `${Math.round(quality.metrics.apply_precision * 100)}% precision in tests · ${quality.metrics.unsafe_false_applies} unsafe suggestions` : 'Checking match quality…'}</span></div></div>
      <div className="tuning-list"><span>Quick actions</span><button onClick={() => { setView('discover'); setMinScore(82); }}>Best matches <ChevronRight size={14} /></button><button onClick={() => { setView('review'); setBucket('watch'); }}>Jobs to review <ChevronRight size={14} /></button><button onClick={() => setView('settings')}>Search settings <ChevronRight size={14} /></button></div>
      <div className="rail-console">{logs.slice(-3).map((line, index) => <span key={`${line}-${index}`}>{line}</span>)}</div>
    </aside>
    <main className="product-workspace">
      {error && <div className="error-banner"><XCircle size={16} /> {error}</div>}
      {view === 'dashboard' && <><section className="page-heading"><div><span className="page-eyebrow">Good {greeting}{candidateName ? `, ${candidateName}` : ''}</span><h1>Your job search, under control.</h1><p>Opportune searches across your roles and locations, then brings the jobs that best match your experience to the top.</p>{data?.profile && <div className="profile-stat-bar"><span className="profile-stat-badge"><Briefcase size={12} /> {data.profile.name}</span><span className="profile-stat-badge success"><CheckCircle2 size={12} /> {data.profile.applied} applied / {data.profile.in_pipeline} in progress</span></div>}</div><div className="heading-stat"><b>{data?.stats.total ?? 0}</b><span>saved jobs</span></div></section><section className="top-section"><div className="section-title"><div><span>Best matches</span><h2>Start with the jobs that fit your experience best</h2></div><button onClick={() => setView('discover')}>Browse all <ChevronRight size={14} /></button></div><div className="top-match-grid">{topJobs.map((job) => <TopMatch job={job} key={job.job_uid} onSelect={setSelectedJob} />)}{!topJobs.length && <DiscoveryEmptyState funnel={funnel} rules={effectiveRules} onRun={runScrape} onSettings={() => setView('settings')} />}</div></section><section className="applications-section"><div className="section-title"><div><span>Saved jobs</span><h2>All jobs in your search</h2></div><div className="inline-pills"><span>{counts.pool} saved</span><span>{counts.apply_now} ready</span><span>{counts.watch} to review</span><span>{counts.active_pipeline} in progress</span></div></div><ReviewTable jobs={reviewJobs} onSelect={setSelectedJob} /></section></>}
      {(view === 'discover' || view === 'review') && <>
        <section className="browse-heading">
          <span className="page-eyebrow">{view === 'review' ? 'Needs your review' : 'Discover'}</span>
          <h1>{view === 'review' ? 'Review before you act.' : 'Find the jobs worth your time.'}</h1>
          <div className="wide-search"><SlidersHorizontal size={17} /><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, company, location, or description…" /></div>
          <div className="filter-row">
            <select aria-label="Freshness" value={freshnessFilter} onChange={(event) => setFreshnessFilter(event.target.value)}><option value="all">Any freshness</option><option value="1">Last 24 hours</option><option value="3">Last 3 days</option><option value="7">Last 7 days</option><option value="14">Last 14 days</option><option value="30">Last 30 days</option><option value="unknown">Unknown date</option></select>

            <div className="pill-toggles">
              {(['all', 'remote', 'hybrid', 'onsite'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={`pill-toggle-btn ${workModeFilter === mode ? 'active' : ''}`}
                  onClick={() => setWorkModeFilter(mode)}
                >
                  {mode === 'all' ? 'All modes' : mode.charAt(0).toUpperCase() + mode.slice(1)}
                </button>
              ))}
            </div>

            <div className="pill-toggles">
              {(['all', 'internship', 'entry_level', 'mid_level', 'senior', 'leadership'] as const).map((level) => (
                <button
                  key={level}
                  type="button"
                  className={`pill-toggle-btn ${experienceFilter === level ? 'active' : ''}`}
                  onClick={() => setExperienceFilter(level)}
                >
                  {level === 'all' ? 'All levels' : level.replace('_', ' ').charAt(0).toUpperCase() + level.replace('_', ' ').slice(1)}
                </button>
              ))}
            </div>

            <div className="pill-toggles">
              {(['all', 'yes', 'no', 'unknown'] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  className={`pill-toggle-btn ${visaFilter === v ? 'active' : ''}`}
                  onClick={() => setVisaFilter(v)}
                >
                  {v === 'all' ? 'Any sponsorship' : v === 'yes' ? 'Sponsorship offered' : v === 'no' ? 'No sponsorship' : 'Sponsorship unknown'}
                </button>
              ))}
            </div>

            <select aria-label="Application status" value={applicationFilter} onChange={(event) => setApplicationFilter(event.target.value)}><option value="not_applied">Not applied</option><option value="active">Applied / active</option><option value="closed">Closed</option><option value="all">Any application status</option></select>
            <select aria-label="Source" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="all">All sources</option>{sources.map((source) => <option value={source} key={source}>{source.replace(/^api_/, '').replace(/_/g, ' ')}</option>)}</select>
            <select aria-label="Match score" value={minScore} onChange={(event) => setMinScore(Number(event.target.value))}><option value="0">Any match score</option><option value="55">55%+ possible</option><option value="82">82%+ strong</option><option value="90">90%+ excellent</option></select>
            <span className="filter-chip"><Database size={13} /> Saved locally</span>
          </div>
        </section>
        <BucketTabs active={view === 'review' && bucket === 'all' ? 'watch' : bucket} counts={counts} onChange={(next) => setBucket(next)} />
        <div className="discover-summary"><span>{visibleJobs.length} opportunities</span><button type="button" onClick={() => { setQuery(''); setSourceFilter('all'); setMinScore(0); setFreshnessFilter('all'); setWorkModeFilter('all'); setExperienceFilter('all'); setVisaFilter('all'); setApplicationFilter('not_applied'); }}><RotateCcw size={13} /> Clear filters</button></div>
        <section className="job-card-grid">{loading ? <div className="dashboard-empty"><RotateCcw className="spin" /> Loading local jobs…</div> : visibleJobs.map((job) => <JobCard job={job} key={job.job_uid} onAction={handleAction} onSelect={setSelectedJob} />)}{!loading && !visibleJobs.length && (uniqueJobs.length ? <div className="dashboard-empty">No jobs match these filters.</div> : <DiscoveryEmptyState funnel={funnel} rules={effectiveRules} onRun={runScrape} onSettings={() => setView('settings')} />)}</section>
      </>}
      {view === 'settings' && <><section className="page-heading settings-heading"><div><span className="page-eyebrow">Settings</span><h1>Shape your search.</h1><p>Update your profile, choose job sources, and manage the data saved on this device.</p></div></section><SettingsPanel onLog={addLog} onReload={loadData} /></>}
    </main>
    {selectedJob && <EvidenceDrawer job={selectedJob} onClose={() => setSelectedJob(null)} onAction={handleAction} />}
  </div>;
}
