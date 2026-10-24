"use client";

import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Cpu, Gauge, Play, RefreshCw, ShieldCheck, TimerReset, TrendingUp, LogOut, Download } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? (
  process.env.NODE_ENV === 'production' ? '' : 'http://localhost:8000'
);
const STORAGE_KEY = 'prontos-auth';

type AuthUser = {
  email: string;
  username: string;
  role: string;
};

type AuthState = {
  token: string;
  user: AuthUser;
};

function getStoredAuth(): AuthState | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      typeof parsed?.token === 'string' &&
      typeof parsed?.user?.email === 'string' &&
      typeof parsed?.user?.username === 'string' &&
      typeof parsed?.user?.role === 'string'
    ) {
      return {
        token: parsed.token,
        user: {
          email: parsed.user.email,
          username: parsed.user.username,
          role: parsed.user.role,
        },
      };
    }
    return null;
  } catch {
    return null;
  }
}

function setStoredAuth(auth: AuthState | null) {
  if (typeof window === 'undefined') return;
  if (auth) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}

export default function Home() {
  const [dashboard, setDashboard] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [runningPolicy, setRunningPolicy] = useState('');
  const [auth, setAuth] = useState<AuthState | null>(getStoredAuth());
  const [loginData, setLoginData] = useState({ email: 'admin@prontos.local', password: 'admin123' });
  const [loginError, setLoginError] = useState('');
  const [users, setUsers] = useState<any[]>([]);
  const [organizations, setOrganizations] = useState<any[]>([]);
  const [userDraft, setUserDraft] = useState({ email: '', username: '', password: '', role: 'viewer' });
  const [organizationDraft, setOrganizationDraft] = useState({
    name: '',
    owner_email: '',
    owner_username: '',
    owner_password: '',
    cpu_quota: '16',
    memory_quota: '12',
    budget_quota: '1000',
  });
  const [quotaDraft, setQuotaDraft] = useState({ cpu_quota: '', memory_quota: '', budget_quota: '' });
  const [reportFilters, setReportFilters] = useState({
    format: 'json',
    status: '',
    category: '',
    policy: '',
    from_date: '',
    to_date: '',
  });
  const [actionMessage, setActionMessage] = useState('');
  const [actionError, setActionError] = useState('');
  const [tutorialDismissed, setTutorialDismissed] = useState(false);
  const [sampleComparison, setSampleComparison] = useState<any>(null);
  const [sampleComparisonLoading, setSampleComparisonLoading] = useState(false);
  const [newExp, setNewExp] = useState({
    name: 'structural-sweep',
    description: 'Parametric structural load sweep',
    category: 'CPU-bound numerical workload',
    cpu: '4',
    memory: '2',
    budget: '12',
    priority: '4',
    estimated_runtime: '26',
    dependencies: '',
    deadline: '2026-10-24',
  });
  const [raceStrategy, setRaceStrategy] = useState({
    strategy_mode: 'optimize',
    race_laps: '57',
    base_lap_time_seconds: '90',
    starting_fuel_kg: '100',
    fuel_burn_per_lap_kg: '1.7',
    fuel_time_penalty_seconds_per_kg: '0.03',
    pit_loss_seconds: '22',
    tire_wear_seconds_per_lap: '0.06',
    max_stint_laps: '35',
    pit_laps: '',
  });

  const authHeaders: Record<string, string> = auth ? { Authorization: `Bearer ${auth.token}` } : {};

  const loadDashboard = async () => {
    if (!auth) {
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/dashboard`, {
        headers: authHeaders,
      });
      if (!resp.ok) {
        throw new Error('Unable to fetch dashboard');
      }
      const data = await resp.json();
      setDashboard(data);
      setQuotaDraft({
        cpu_quota: String(data.organization.cpu_quota),
        memory_quota: String(data.organization.memory_quota),
        budget_quota: String(data.organization.budget_quota),
      });
      if (['admin', 'platform_admin'].includes(auth.user.role)) {
        const userResponse = await fetch(`${API_BASE}/api/admin/users`, { headers: authHeaders });
        if (!userResponse.ok) throw new Error('Unable to load organization users');
        setUsers(await userResponse.json());
      } else {
        setUsers([]);
      }
      if (auth.user.role === 'platform_admin') {
        const organizationResponse = await fetch(`${API_BASE}/api/admin/organizations`, { headers: authHeaders });
        if (!organizationResponse.ok) throw new Error('Unable to load organizations');
        setOrganizations(await organizationResponse.json());
      } else {
        setOrganizations([]);
      }
    } catch (error) {
      setAuth(null);
      setStoredAuth(null);
      setLoginError('Your session expired. Please sign in again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (auth) {
      setTutorialDismissed(window.localStorage.getItem(`prontos-tutorial-dismissed:${auth.user.email}`) === 'true');
      loadDashboard();
    } else {
      setLoading(false);
    }
  }, [auth]);

  const chartData = useMemo(() => {
    const policies = dashboard?.comparison ?? [];
    return policies.map((x: any) => ({
      name: x.policy,
      value: x.completed_jobs,
      makespan: x.makespan,
      score: x.score,
    }));
  }, [dashboard]);

  const bestPolicy = useMemo(() => {
    const policies = dashboard?.comparison ?? [];
    if (!policies.length) return null;
    return [...policies].sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || (b.completed_jobs ?? 0) - (a.completed_jobs ?? 0))[0];
  }, [dashboard]);

  const readinessSummary = useMemo(() => {
    const experiments = dashboard?.experiments ?? [];
    const independent = experiments.filter((exp: any) => !exp.dependencies || exp.dependencies.length === 0).length;
    const dependencies = experiments.filter((exp: any) => exp.dependencies && exp.dependencies.length > 0).length;
    const pendingExperiments = experiments.filter((exp: any) => ['ready', 'queued', 'running'].includes(exp.status));
    const urgent = [...pendingExperiments].sort((a: any, b: any) => {
      const da = a.deadline || '9999-12-31';
      const dbd = b.deadline || '9999-12-31';
      return da.localeCompare(dbd);
    })[0];

    return { independent, dependencies, urgent };
  }, [dashboard]);

  const analytics = dashboard?.analytics ?? {
    total_cpu: 0,
    total_memory: 0,
    eligible_cpu: 0,
    eligible_memory: 0,
    eligible_percentage: 0,
    ready_count: 0,
  };

  const handleLogin = async () => {
    setLoginError('');
    try {
      const resp = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(loginData),
      });
      const payload = await resp.json();
      if (!resp.ok) {
        throw new Error(payload.detail || 'Login failed');
      }
      setLoading(true);
      setAuth(payload);
      setStoredAuth(payload);
    } catch (error: any) {
      setLoginError(error.message || 'Login failed');
    }
  };

  const handleLogout = () => {
    setAuth(null);
    setStoredAuth(null);
    setLoginError('');
  };

  const handleRunPolicy = async (policy: string) => {
    if (!auth) return;
    setActionError('');
    setActionMessage('');
    setRunningPolicy(policy);
    try {
      const response = await fetch(`${API_BASE}/api/scheduler/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ policy }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || result.message || 'Scheduling failed');
      setActionMessage(result.message);
      await loadDashboard();
    } catch (error: any) {
      setActionError(error.message || 'Scheduling failed');
    } finally {
      setRunningPolicy('');
    }
  };

  const handleCreateExperiment = async () => {
    if (!auth) return;
    setActionError('');
    setActionMessage('');
    try {
      const resp = await fetch(`${API_BASE}/api/experiments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({
          ...newExp,
          cpu: Number(newExp.cpu),
          memory: Number(newExp.memory),
          budget: Number(newExp.budget),
          priority: Number(newExp.priority),
          estimated_runtime: Number(newExp.estimated_runtime),
          deadline: newExp.deadline || null,
          dependencies: newExp.dependencies.split(',').map((d) => d.trim()).filter(Boolean),
          ...(newExp.category === 'Race strategy simulation' ? {
            race_strategy: {
              strategy_mode: raceStrategy.strategy_mode,
              race_laps: Number(raceStrategy.race_laps),
              base_lap_time_seconds: Number(raceStrategy.base_lap_time_seconds),
              starting_fuel_kg: Number(raceStrategy.starting_fuel_kg),
              fuel_burn_per_lap_kg: Number(raceStrategy.fuel_burn_per_lap_kg),
              fuel_time_penalty_seconds_per_kg: Number(raceStrategy.fuel_time_penalty_seconds_per_kg),
              pit_loss_seconds: Number(raceStrategy.pit_loss_seconds),
              tire_wear_seconds_per_lap: Number(raceStrategy.tire_wear_seconds_per_lap),
              max_stint_laps: Number(raceStrategy.max_stint_laps),
              ...(raceStrategy.strategy_mode === 'manual' ? {
                pit_laps: raceStrategy.pit_laps.trim()
                  ? raceStrategy.pit_laps.split(',').map((lap) => Number(lap.trim()))
                  : [],
              } : {}),
            },
          } : {}),
        }),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.detail || 'Unable to create experiment');
      setActionMessage(`Created experiment ${result.id}.`);
      await loadDashboard();
    } catch (error: any) {
      setActionError(error.message || 'Unable to create experiment');
    }
  };

  const handleLoadRaceSample = async () => {
    if (!auth) return;
    setActionError('');
    setSampleComparisonLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/reference/bahrain-2024`, { headers: authHeaders });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Unable to load the Bahrain sample');
      setSampleComparison(result);
    } catch (error: any) {
      setActionError(error.message || 'Unable to load the Bahrain sample');
    } finally {
      setSampleComparisonLoading(false);
    }
  };

  const handlePrepareRaceSample = () => {
    setNewExp({
      name: 'bahrain-2024-strategy-practice',
      description: 'Unvalidated strategy-model practice using an observed Bahrain race as context',
      category: 'Race strategy simulation',
      cpu: '1',
      memory: '1',
      budget: '1',
      priority: '4',
      estimated_runtime: '1',
      dependencies: '',
      deadline: '',
    });
    setRaceStrategy({
      strategy_mode: 'optimize',
      race_laps: '57',
      base_lap_time_seconds: '95.6',
      starting_fuel_kg: '100',
      fuel_burn_per_lap_kg: '1.7',
      fuel_time_penalty_seconds_per_kg: '0',
      pit_loss_seconds: '22',
      tire_wear_seconds_per_lap: '0.06',
      max_stint_laps: '35',
      pit_laps: '',
    });
    document.getElementById('create-experiment')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const dismissTutorial = () => {
    setTutorialDismissed(true);
    if (auth) {
      window.localStorage.setItem(`prontos-tutorial-dismissed:${auth.user.email}`, 'true');
    }
  };

  const handleResetDemo = async () => {
    if (!auth) return;
    setActionError('');
    try {
      const response = await fetch(`${API_BASE}/api/demo/reset`, {
        method: 'POST',
        headers: authHeaders,
      });
      if (!response.ok) throw new Error('Unable to reset demo data');
      setActionMessage('Demo workspace has been reset.');
      await loadDashboard();
    } catch (error: any) {
      setActionError(error.message || 'Unable to reset demo data');
    }
  };

  const handleExport = async () => {
    if (!auth) return;
    setActionError('');
    try {
      const query = new URLSearchParams();
      Object.entries(reportFilters).forEach(([key, value]) => {
        if (value) query.set(key, value);
      });
      const response = await fetch(`${API_BASE}/api/export/benchmark?${query}`, {
        headers: authHeaders,
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || 'Benchmark export failed');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = reportFilters.format === 'csv' ? 'prontos-benchmark.csv' : 'prontos-benchmark.json';
      link.click();
      URL.revokeObjectURL(url);
      setActionMessage('Benchmark report downloaded.');
    } catch (error: any) {
      setActionError(error.message || 'Benchmark export failed');
    }
  };

  const handleCreateUser = async () => {
    if (!auth) return;
    setActionError('');
    try {
      const response = await fetch(`${API_BASE}/api/admin/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify(userDraft),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Unable to create user');
      setUserDraft({ email: '', username: '', password: '', role: 'viewer' });
      setActionMessage(`Added ${result.username} to this organization.`);
      await loadDashboard();
    } catch (error: any) {
      setActionError(error.message || 'Unable to create user');
    }
  };

  const handleUpdateUser = async (userId: string, update: Record<string, unknown>) => {
    if (!auth) return;
    setActionError('');
    try {
      const response = await fetch(`${API_BASE}/api/admin/users/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify(update),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Unable to update user');
      setActionMessage(`Updated ${result.username}.`);
      await loadDashboard();
    } catch (error: any) {
      setActionError(error.message || 'Unable to update user');
    }
  };

  const handleCreateOrganization = async () => {
    if (!auth) return;
    setActionError('');
    try {
      const response = await fetch(`${API_BASE}/api/admin/organizations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({
          ...organizationDraft,
          cpu_quota: Number(organizationDraft.cpu_quota),
          memory_quota: Number(organizationDraft.memory_quota),
          budget_quota: Number(organizationDraft.budget_quota),
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Unable to create organization');
      setActionMessage(`Created ${result.organization.name}. Its owner can now sign in.`);
      await loadDashboard();
    } catch (error: any) {
      setActionError(error.message || 'Unable to create organization');
    }
  };

  const handleUpdateQuotas = async () => {
    if (!auth) return;
    setActionError('');
    try {
      const response = await fetch(`${API_BASE}/api/admin/organization`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({
          cpu_quota: Number(quotaDraft.cpu_quota),
          memory_quota: Number(quotaDraft.memory_quota),
          budget_quota: Number(quotaDraft.budget_quota),
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Unable to update quotas');
      setActionMessage('Organization quotas updated.');
      await loadDashboard();
    } catch (error: any) {
      setActionError(error.message || 'Unable to update quotas');
    }
  };

  const stats = dashboard?.summary ?? {
    completed_jobs: 0,
    active_jobs: 0,
    failed_jobs: 0,
    avg_runtime: 0,
    budget_usage: 0,
  };
  const canAdminister = auth && ['admin', 'platform_admin'].includes(auth.user.role);
  const canOperate = auth && ['operator', 'admin', 'platform_admin'].includes(auth.user.role);

  if (!auth) {
    return (
      <main className="min-h-screen bg-slate-950 p-6 text-slate-50">
        <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">
          <p className="text-xs uppercase tracking-[0.24em] text-amber-400">PRONTOS access</p>
          <h1 className="mt-3 text-3xl font-semibold">Secure operator portal</h1>
          <div className="mt-6 space-y-4">
            <Field label="Email" value={loginData.email} onChange={(value) => setLoginData({ ...loginData, email: value })} />
            <Field label="Password" type="password" value={loginData.password} onChange={(value) => setLoginData({ ...loginData, password: value })} />
            {loginError ? <div className="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">{loginError}</div> : null}
            <button onClick={handleLogin} className="w-full rounded-md bg-amber-500 px-4 py-2 font-semibold text-slate-950">Sign in</button>
            <div className="rounded-md border border-slate-700 bg-slate-950/70 p-3 text-sm text-slate-300">
              Demo credentials: admin@prontos.local / admin123
            </div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-6 md:p-10">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8 flex flex-col gap-4 border-b border-slate-800 pb-6 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-amber-400">Simulation orchestration</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-50">PRONTOS</h1>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs uppercase tracking-[0.18em] text-slate-300">
              {auth.user.role}
            </div>
            {canAdminister ? (
              <button
                onClick={handleResetDemo}
                className="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-100"
              >
                <RefreshCw className="h-4 w-4" /> Reset workspace
              </button>
            ) : null}
            <button
              onClick={handleExport}
              className="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-100"
            >
              <Download className="h-4 w-4" /> Export
            </button>
            <button
              onClick={handleLogout}
              className="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-100"
            >
              <LogOut className="h-4 w-4" /> Logout
            </button>
            {canOperate ? (
              <button
                onClick={() => handleRunPolicy('adaptive')}
                disabled={Boolean(runningPolicy)}
                className="inline-flex items-center gap-2 rounded-md bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-60"
              >
                <Play className="h-4 w-4" /> {runningPolicy ? 'Running...' : 'Run adaptive'}
              </button>
            ) : null}
          </div>
        </header>

        {loading || !dashboard ? <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-6 text-slate-400">Loading PRONTOS…</div> : (
          <>
            {actionError ? <div role="alert" className="mb-5 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">{actionError}</div> : null}
            {actionMessage ? <div role="status" className="mb-5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{actionMessage}</div> : null}
            {tutorialDismissed ? (
              <div className="mb-5 text-right">
                <button
                  onClick={() => {
                    setTutorialDismissed(false);
                    window.localStorage.removeItem(`prontos-tutorial-dismissed:${auth.user.email}`);
                  }}
                  className="text-sm text-amber-300 underline underline-offset-4"
                >
                  Show first-time race strategy guide
                </button>
              </div>
            ) : (
              <section aria-labelledby="race-guide-title" className="mb-8 rounded-xl border border-amber-700/50 bg-amber-950/20 p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-300">First-time guide · 3 steps</p>
                    <h2 id="race-guide-title" className="mt-1 text-lg font-semibold text-slate-50">Try a race-strategy example</h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
                      Think of this as a classroom calculator: it explores pit-stop assumptions, not a real car or race. The model has not been validated for race decisions.
                    </p>
                  </div>
                  <button onClick={dismissTutorial} className="text-sm text-slate-400 underline underline-offset-4">
                    Dismiss guide
                  </button>
                </div>
                <ol className="mt-4 grid gap-3 md:grid-cols-3">
                  <li className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                    <p className="text-sm font-semibold text-slate-100">1. Look at a real example</p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">Load observed 2024 Bahrain lap times and tire stints from the bundled historical sample.</p>
                    <button
                      onClick={handleLoadRaceSample}
                      disabled={sampleComparisonLoading}
                      className="mt-3 rounded-md border border-amber-500/50 px-3 py-2 text-xs font-semibold text-amber-200 disabled:opacity-50"
                    >
                      {sampleComparisonLoading ? 'Loading sample…' : sampleComparison ? 'Refresh sample' : 'Load Bahrain sample'}
                    </button>
                  </li>
                  <li className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                    <p className="text-sm font-semibold text-slate-100">2. Compare, don’t grade</p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">See the observed pit pattern beside the prototype’s assumption-based suggestions. A difference is a clue, not a verdict.</p>
                  </li>
                  <li className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                    <p className="text-sm font-semibold text-slate-100">3. Try it yourself</p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">Load a sample setup into the experiment form, create it, then run the scheduler to inspect lap-by-lap output.</p>
                    {canOperate ? (
                      <button
                        onClick={handlePrepareRaceSample}
                        className="mt-3 rounded-md border border-slate-600 px-3 py-2 text-xs font-semibold text-slate-100"
                      >
                        Prepare sample experiment
                      </button>
                    ) : (
                      <p className="mt-3 text-xs text-slate-500">An operator role is needed to create and run an experiment.</p>
                    )}
                  </li>
                </ol>
                {sampleComparison ? (
                  <div className="mt-4 rounded-lg border border-amber-700/40 bg-slate-950/70 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-semibold text-slate-100">
                        {sampleComparison.reference.event_name} · {sampleComparison.reference.driver_name}
                      </h3>
                      <span className="rounded-full border border-amber-700/50 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-amber-300">
                        Exploratory only · not validation
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-slate-300">
                      Observed: {sampleComparison.reference.lap_count} laps, pit stops after laps {sampleComparison.reference.observed_pit_after_laps.join(' and ')}.
                      {' '}Median non-pit-out lap: {sampleComparison.reference.median_lap_time_seconds_excluding_pit_out}s.
                    </p>
                    <div className="mt-3 overflow-x-auto">
                      <table className="w-full min-w-[620px] text-left text-xs">
                        <thead className="text-slate-400">
                          <tr>
                            <th className="py-2 pr-3">Observed stint</th>
                            <th className="py-2 pr-3">Laps</th>
                            <th className="py-2 pr-3">Tire</th>
                            <th className="py-2 pr-3">Median lap</th>
                            <th className="py-2">Prototype sensitivity suggestion</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sampleComparison.reference.stints.map((stint: any, index: number) => (
                            <tr key={stint.stint_number} className="border-t border-slate-800 text-slate-300">
                              <td className="py-2 pr-3">Stint {stint.stint_number}</td>
                              <td className="py-2 pr-3">{stint.lap_start}–{stint.lap_end} ({stint.lap_count})</td>
                              <td className="py-2 pr-3">{stint.tire_compound}</td>
                              <td className="py-2 pr-3">{stint.median_lap_time_seconds_excluding_pit_out ?? '—'}s</td>
                              {index === 0 ? (
                                <td rowSpan={sampleComparison.reference.stints.length} className="py-2 align-middle text-amber-200">
                                  {sampleComparison.strategy_scenarios[0]?.suggested_stop_count} stop after lap {sampleComparison.strategy_scenarios[0]?.suggested_pit_laps.join(', ') || 'none'} in {sampleComparison.strategy_scenarios.length} illustrative settings
                                  <div className="mt-1 font-semibold">
                                    {sampleComparison.strategy_scenarios.filter((scenario: any) => scenario.matches_observed_pit_laps).length}/{sampleComparison.strategy_scenarios.length} matched observed pit laps
                                  </div>
                                </td>
                              ) : null}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="mt-3 text-xs leading-5 text-slate-400">{sampleComparison.interpretation}</p>
                    <p className="mt-2 text-[11px] text-slate-500">Source: {sampleComparison.reference.data_source}. Historical data is shown for education/research; check provider terms before reuse.</p>
                  </div>
                ) : null}
              </section>
            )}
            <section className="mb-8 rounded-xl border border-slate-800 bg-slate-900/70 p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-50">Benchmark report</h2>
                  <p className="mt-1 text-sm text-slate-400">Export this organization’s filtered queue and policy results.</p>
                </div>
                <button onClick={handleExport} className="inline-flex items-center gap-2 rounded-md bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-950">
                  <Download className="h-4 w-4" /> Download report
                </button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
                <SelectField label="Format" value={reportFilters.format} onChange={(value) => setReportFilters({ ...reportFilters, format: value })} options={[['json', 'JSON'], ['csv', 'CSV']]} />
                <SelectField label="Status" value={reportFilters.status} onChange={(value) => setReportFilters({ ...reportFilters, status: value })} options={[['', 'All'], ['ready', 'Ready'], ['completed', 'Completed'], ['failed', 'Failed']]} />
                <Field label="Category" value={reportFilters.category} onChange={(value) => setReportFilters({ ...reportFilters, category: value })} />
                <SelectField label="Policy" value={reportFilters.policy} onChange={(value) => setReportFilters({ ...reportFilters, policy: value })} options={[['', 'All'], ['fifo', 'FIFO'], ['priority', 'Priority'], ['shortest', 'Shortest'], ['deadline', 'Deadline'], ['adaptive', 'Adaptive']]} />
                <Field label="Created from" type="date" value={reportFilters.from_date} onChange={(value) => setReportFilters({ ...reportFilters, from_date: value })} />
                <Field label="Created to" type="date" value={reportFilters.to_date} onChange={(value) => setReportFilters({ ...reportFilters, to_date: value })} />
              </div>
            </section>
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <StatCard icon={<Gauge className="h-4 w-4" />} label="Completed jobs" value={stats.completed_jobs} tone="amber" />
              <StatCard icon={<Cpu className="h-4 w-4" />} label="Active jobs" value={stats.active_jobs} tone="sky" />
              <StatCard icon={<TimerReset className="h-4 w-4" />} label="Avg runtime" value={`${stats.avg_runtime.toFixed(1)}h`} tone="violet" />
              <StatCard icon={<ShieldCheck className="h-4 w-4" />} label="Failed jobs" value={stats.failed_jobs} tone="red" />
              <StatCard icon={<TrendingUp className="h-4 w-4" />} label="Budget committed" value={`${stats.budget_usage.toFixed(0)}%`} tone="emerald" />
            </section>

            <section className="mt-8 grid gap-4 lg:grid-cols-4">
              <InsightCard title="Recommended policy" value={bestPolicy ? bestPolicy.policy.toUpperCase() : 'N/A'} detail={bestPolicy ? `Score ${bestPolicy.score.toFixed(1)} · ${bestPolicy.completed_jobs} jobs` : 'No comparison data'} accent="amber" />
              <InsightCard title="Dependency readiness" value={`${readinessSummary.independent} ready`} detail={`${readinessSummary.dependencies} experiments depend on upstream work`} accent="sky" />
              <InsightCard title="Urgent deadline" value={readinessSummary.urgent ? readinessSummary.urgent.name : 'None'} detail={readinessSummary.urgent ? `Due ${readinessSummary.urgent.deadline}` : 'No deadlines assigned'} accent="violet" />
              <InsightCard title="Eligible CPU / capacity" value={`${analytics.eligible_percentage.toFixed(0)}%`} detail={`${analytics.ready_count} experiments eligible · ${analytics.eligible_cpu.toFixed(1)} CPU / ${analytics.eligible_memory.toFixed(1)} memory`} accent="amber" />
            </section>

            <section className="mt-8 grid gap-6 xl:grid-cols-[1.4fr_0.6fr]">
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 shadow-panel">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-50">Scheduling policy comparison</h2>
                  {canOperate ? <div className="flex gap-2">
                    {['fifo', 'priority', 'shortest', 'deadline', 'adaptive'].map((policy) => (
                      <button
                        key={policy}
                        onClick={() => handleRunPolicy(policy)}
                        disabled={Boolean(runningPolicy)}
                        className={`rounded-md border px-2 py-1 text-xs font-medium ${runningPolicy === policy ? 'border-amber-400 text-amber-300' : 'border-slate-700 text-slate-300'}`}
                      >
                        {policy}
                      </button>
                    ))}
                  </div> : null}
                </div>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData}>
                      <CartesianGrid stroke="#334155" vertical={false} />
                      <XAxis dataKey="name" stroke="#94a3b8" tickLine={false} axisLine={false} />
                      <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
                      <Tooltip />
                      <Bar dataKey="value" fill="#f59e0b" radius={[4,4,0,0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-5 space-y-3">
                  {(dashboard?.comparison ?? []).map((policyData: any) => (
                    <div key={policyData.policy} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.20em] text-slate-300">
                        <span>{policyData.policy}</span>
                        <span>{policyData.completed_jobs} jobs</span>
                      </div>
                      <div className="mt-2 text-sm text-slate-200">{policyData.explanation}</div>
                    </div>
                  ))}
                </div>
              </div>

              {canOperate ? <div id="create-experiment" className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 shadow-panel">
                <h2 className="mb-4 text-lg font-semibold text-slate-50">Create experiment</h2>
                <div className="space-y-3">
                  <Field label="Name" value={newExp.name} onChange={(v) => setNewExp({ ...newExp, name: v })} />
                  <Field label="Description" value={newExp.description} onChange={(v) => setNewExp({ ...newExp, description: v })} />
                  <SelectField
                    label="Category"
                    value={newExp.category}
                    onChange={(v) => setNewExp({ ...newExp, category: v })}
                    options={[
                      ['CPU-bound numerical workload', 'CPU-bound numerical workload'],
                      ['Monte Carlo experiment', 'Monte Carlo experiment'],
                      ['Parameter sweep', 'Parameter sweep'],
                      ['Synthetic vehicle or engineering simulation', 'Synthetic vehicle simulation (demo)'],
                      ['Deliberately failing workload for testing recovery', 'Deliberately failing workload (test)'],
                      ['Race strategy simulation', 'Race strategy simulation (unvalidated)'],
                    ]}
                  />
                  {newExp.category === 'Race strategy simulation' ? (
                    <div className="space-y-3 rounded-lg border border-amber-700/50 bg-amber-950/20 p-3">
                      <p className="text-xs leading-5 text-amber-200">
                        Strategy model only; not calibrated or validated for real racing. Assumptions omit weather, traffic, safety cars, and incidents.
                      </p>
                      <SelectField
                        label="Strategy mode"
                        value={raceStrategy.strategy_mode}
                        onChange={(value) => setRaceStrategy({ ...raceStrategy, strategy_mode: value })}
                        options={[['optimize', 'Optimize pit laps'], ['manual', 'Manual pit laps']]}
                      />
                      {raceStrategy.strategy_mode === 'manual' ? (
                        <Field
                          label="Pit after laps (comma separated)"
                          value={raceStrategy.pit_laps}
                          onChange={(value) => setRaceStrategy({ ...raceStrategy, pit_laps: value })}
                        />
                      ) : null}
                      <div className="grid grid-cols-2 gap-3">
                        <Field label="Race laps" type="number" value={raceStrategy.race_laps} onChange={(value) => setRaceStrategy({ ...raceStrategy, race_laps: value })} />
                        <Field label="Base lap time (seconds)" type="number" value={raceStrategy.base_lap_time_seconds} onChange={(value) => setRaceStrategy({ ...raceStrategy, base_lap_time_seconds: value })} />
                        <Field label="Starting fuel (kg)" type="number" value={raceStrategy.starting_fuel_kg} onChange={(value) => setRaceStrategy({ ...raceStrategy, starting_fuel_kg: value })} />
                        <Field label="Fuel burn / lap (kg)" type="number" value={raceStrategy.fuel_burn_per_lap_kg} onChange={(value) => setRaceStrategy({ ...raceStrategy, fuel_burn_per_lap_kg: value })} />
                        <Field label="Fuel time penalty (s/kg)" type="number" value={raceStrategy.fuel_time_penalty_seconds_per_kg} onChange={(value) => setRaceStrategy({ ...raceStrategy, fuel_time_penalty_seconds_per_kg: value })} />
                        <Field label="Pit loss (seconds)" type="number" value={raceStrategy.pit_loss_seconds} onChange={(value) => setRaceStrategy({ ...raceStrategy, pit_loss_seconds: value })} />
                        <Field label="Tire wear (s/lap of age)" type="number" value={raceStrategy.tire_wear_seconds_per_lap} onChange={(value) => setRaceStrategy({ ...raceStrategy, tire_wear_seconds_per_lap: value })} />
                        <Field label="Maximum stint (laps)" type="number" value={raceStrategy.max_stint_laps} onChange={(value) => setRaceStrategy({ ...raceStrategy, max_stint_laps: value })} />
                      </div>
                    </div>
                  ) : null}
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="CPU" type="number" value={newExp.cpu} onChange={(v) => setNewExp({ ...newExp, cpu: v })} />
                    <Field label="Memory" type="number" value={newExp.memory} onChange={(v) => setNewExp({ ...newExp, memory: v })} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Priority" type="number" value={newExp.priority} onChange={(v) => setNewExp({ ...newExp, priority: v })} />
                    <Field label="Budget" type="number" value={newExp.budget} onChange={(v) => setNewExp({ ...newExp, budget: v })} />
                  </div>
                  <Field label="Estimated runtime" type="number" value={newExp.estimated_runtime} onChange={(v) => setNewExp({ ...newExp, estimated_runtime: v })} />
                  <Field label="Deadline" type="date" value={newExp.deadline} onChange={(v) => setNewExp({ ...newExp, deadline: v })} />
                  <Field label="Dependencies (comma separated)" value={newExp.dependencies} onChange={(v) => setNewExp({ ...newExp, dependencies: v })} />
                  <button onClick={handleCreateExperiment} className="w-full rounded-md bg-slate-100 px-3 py-2 text-sm font-semibold text-slate-950">Add experiment</button>
                </div>
              </div> : null}
            </section>

            <section className="mt-8 grid gap-6 xl:grid-cols-[1fr_1fr]">
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <h2 className="mb-4 text-lg font-semibold text-slate-50">Resource demand</h2>
                <div className="space-y-4">
                  <div>
                    <div className="mb-1 flex items-center justify-between text-sm text-slate-300">
                      <span>Eligible CPU / worker capacity</span>
                      <span>{analytics.eligible_percentage.toFixed(0)}%</span>
                    </div>
                    <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
                      <div className="h-full rounded-full bg-amber-500" style={{ width: `${Math.min(analytics.eligible_percentage, 100)}%` }} />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm text-slate-300">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Total CPU</div>
                      <div className="mt-2 text-xl font-semibold text-white">{analytics.total_cpu.toFixed(1)}</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Total memory</div>
                      <div className="mt-2 text-xl font-semibold text-white">{analytics.total_memory.toFixed(1)}</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Eligible CPU</div>
                      <div className="mt-2 text-xl font-semibold text-white">{analytics.eligible_cpu.toFixed(1)}</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Eligible memory</div>
                      <div className="mt-2 text-xl font-semibold text-white">{analytics.eligible_memory.toFixed(1)}</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <h2 className="mb-4 text-lg font-semibold text-slate-50">Operational note</h2>
                <p className="text-sm text-slate-300">
                  {analytics.ready_count > 0
                    ? `The current queue has ${analytics.ready_count} ready experiments with ${analytics.eligible_cpu.toFixed(1)} CPU and ${analytics.eligible_memory.toFixed(1)} memory demand, suggesting a moderate scheduling pressure for the live worker pool.`
                    : 'No experiments are currently eligible for scheduling.'}
                </p>
              </div>
            </section>

            <section className="mt-8 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <h2 className="mb-4 text-lg font-semibold text-slate-50">Experiment queue</h2>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="text-slate-400">
                      <tr>
                        <th className="pb-3 pr-3">Name</th>
                        <th className="pb-3 pr-3">Type</th>
                        <th className="pb-3 pr-3">Priority</th>
                        <th className="pb-3 pr-3">Runtime</th>
                        <th className="pb-3 pr-3">Deadline</th>
                        <th className="pb-3 pr-3">Deps</th>
                        <th className="pb-3">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(dashboard?.experiments ?? []).map((exp: any) => (
                        <tr key={exp.id} className="border-t border-slate-800 align-top">
                          <td className="py-3 pr-3 text-slate-100">{exp.name}</td>
                          <td className="py-3 pr-3 text-slate-300">{exp.category}</td>
                          <td className="py-3 pr-3 text-slate-300">{exp.priority}</td>
                          <td className="py-3 pr-3 text-slate-300">{exp.estimated_runtime}h</td>
                          <td className="py-3 pr-3 text-slate-300">{exp.deadline || '—'}</td>
                          <td className="py-3 pr-3 text-slate-300">{exp.dependencies?.length ? exp.dependencies.join(', ') : 'None'}</td>
                          <td className="py-3"><StatusPill status={exp.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <h2 className="mb-4 text-lg font-semibold text-slate-50">Recent dispatches</h2>
                <div className="space-y-3">
                  {(dashboard?.timeline ?? []).map((step: any) => (
                    <div key={step.id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-slate-400">
                        <span>{step.policy}</span>
                        <span>{step.status}</span>
                      </div>
                      <div className="mt-2 text-sm text-slate-100">{step.reason}</div>
                      {step.result ? (
                        <div className="mt-3 border-t border-slate-800 pt-3 text-xs text-slate-300">
                          <div>
                            {step.result.race_laps} laps · {step.result.total_race_time_seconds}s total · {step.result.average_lap_time_seconds}s average · {step.result.pit_stops} pit stops
                          </div>
                          <div className="mt-1">
                            Pit after laps: {step.result.pit_laps.length ? step.result.pit_laps.join(', ') : 'none'}
                          </div>
                          <div className="mt-1 font-semibold text-amber-300">
                            {step.result.validation_status} · {step.result.model}
                          </div>
                          <details className="mt-2">
                            <summary className="cursor-pointer text-slate-200">View lap-by-lap output</summary>
                            <div className="mt-2 max-h-48 overflow-auto">
                              <table className="w-full text-left">
                                <thead className="sticky top-0 bg-slate-950 text-slate-400">
                                  <tr>
                                    <th className="py-1 pr-3">Lap</th>
                                    <th className="py-1 pr-3">Time (s)</th>
                                    <th className="py-1 pr-3">Fuel (kg)</th>
                                    <th className="py-1 pr-3">Tire age</th>
                                    <th className="py-1">Pit</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {step.result.laps.map((lap: any) => (
                                    <tr key={lap.lap} className="border-t border-slate-800">
                                      <td className="py-1 pr-3">{lap.lap}</td>
                                      <td className="py-1 pr-3">{lap.lap_time_seconds}</td>
                                      <td className="py-1 pr-3">{lap.fuel_before_lap_kg}</td>
                                      <td className="py-1 pr-3">{lap.tire_age_laps}</td>
                                      <td className="py-1">{lap.pit_stop ? 'Yes' : '—'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </details>
                        </div>
                      ) : null}
                    </div>
                  ))}
                  {(dashboard?.timeline ?? []).length === 0 ? (
                    <p className="text-sm text-slate-400">No jobs have been dispatched in this organization yet.</p>
                  ) : null}
                </div>
              </div>
            </section>

            <section className="mt-8 grid gap-6 xl:grid-cols-2">
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-50">Worker pool</h2>
                    <p className="mt-1 text-sm text-slate-400">
                      {dashboard.worker_capacity.online_workers} of {dashboard.worker_capacity.worker_count} online
                    </p>
                  </div>
                  <span className="text-sm text-slate-300">
                    {dashboard.worker_capacity.cpu_total} CPU · {dashboard.worker_capacity.memory_total} memory
                  </span>
                </div>
                <div className="space-y-3">
                  {dashboard.workers.map((worker: any) => (
                    <div key={worker.id} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div>
                        <div className="font-medium text-slate-100">{worker.name}</div>
                        <div className="mt-1 text-xs text-slate-400">{worker.cpu_capacity} CPU · {worker.memory_capacity} memory</div>
                      </div>
                      <StatusPill status={worker.status} />
                    </div>
                  ))}
                  {dashboard.workers.length === 0 ? <p className="text-sm text-slate-400">No workers provisioned.</p> : null}
                </div>
              </div>

              {canAdminister ? (
                <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                  <h2 className="text-lg font-semibold text-slate-50">Organization quotas</h2>
                  <p className="mt-1 text-sm text-slate-400">{dashboard.organization.name}</p>
                  <div className="mt-4 grid grid-cols-3 gap-3">
                    <Field label="CPU quota" type="number" value={quotaDraft.cpu_quota} onChange={(value) => setQuotaDraft({ ...quotaDraft, cpu_quota: value })} />
                    <Field label="Memory quota" type="number" value={quotaDraft.memory_quota} onChange={(value) => setQuotaDraft({ ...quotaDraft, memory_quota: value })} />
                    <Field label="Budget quota" type="number" value={quotaDraft.budget_quota} onChange={(value) => setQuotaDraft({ ...quotaDraft, budget_quota: value })} />
                  </div>
                  <button onClick={handleUpdateQuotas} className="mt-4 rounded-md bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-950">
                    Save quotas
                  </button>
                </div>
              ) : null}
            </section>

            {canAdminister ? (
              <section className="mt-8 rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <h2 className="text-lg font-semibold text-slate-50">Organization users</h2>
                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="text-slate-400">
                      <tr>
                        <th className="pb-3 pr-4">User</th>
                        <th className="pb-3 pr-4">Role</th>
                        <th className="pb-3 pr-4">Access</th>
                        <th className="pb-3">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((user) => (
                        <tr key={user.id} className="border-t border-slate-800">
                          <td className="py-3 pr-4">
                            <div className="text-slate-100">{user.username}</div>
                            <div className="text-xs text-slate-400">{user.email}</div>
                          </td>
                          <td className="py-3 pr-4">
                            <SelectField
                              label="Role"
                              value={user.role === 'platform_admin' ? 'admin' : user.role}
                              onChange={(role) => handleUpdateUser(user.id, { role })}
                              options={[['viewer', 'Viewer'], ['operator', 'Operator'], ['admin', 'Admin']]}
                              disabled={user.role === 'platform_admin' || user.email === auth.user.email}
                            />
                          </td>
                          <td className="py-3 pr-4"><StatusPill status={user.is_active ? 'online' : 'failed'} /></td>
                          <td className="py-3">
                            {user.role === 'platform_admin' || user.email === auth.user.email ? 'Protected account' : (
                              <button
                                onClick={() => handleUpdateUser(user.id, { is_active: !user.is_active })}
                                className="rounded border border-slate-700 px-3 py-1 text-xs text-slate-200"
                              >
                                {user.is_active ? 'Deactivate' : 'Activate'}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                  <Field label="Email" value={userDraft.email} onChange={(value) => setUserDraft({ ...userDraft, email: value })} />
                  <Field label="Username" value={userDraft.username} onChange={(value) => setUserDraft({ ...userDraft, username: value })} />
                  <Field label="Temporary password (12+ chars)" type="password" value={userDraft.password} onChange={(value) => setUserDraft({ ...userDraft, password: value })} />
                  <SelectField label="Role" value={userDraft.role} onChange={(role) => setUserDraft({ ...userDraft, role })} options={[['viewer', 'Viewer'], ['operator', 'Operator'], ['admin', 'Admin']]} />
                  <button onClick={handleCreateUser} className="self-end rounded-md bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-950">
                    Add user
                  </button>
                </div>
              </section>
            ) : null}

            {auth.user.role === 'platform_admin' ? (
              <section className="mt-8 rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <h2 className="text-lg font-semibold text-slate-50">Create organization</h2>
                <p className="mt-1 text-sm text-slate-400">Provision a new isolated workspace and its initial administrator.</p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Field label="Organization name" value={organizationDraft.name} onChange={(value) => setOrganizationDraft({ ...organizationDraft, name: value })} />
                  <Field label="Owner email" value={organizationDraft.owner_email} onChange={(value) => setOrganizationDraft({ ...organizationDraft, owner_email: value })} />
                  <Field label="Owner username" value={organizationDraft.owner_username} onChange={(value) => setOrganizationDraft({ ...organizationDraft, owner_username: value })} />
                  <Field label="Owner password (12+ chars)" type="password" value={organizationDraft.owner_password} onChange={(value) => setOrganizationDraft({ ...organizationDraft, owner_password: value })} />
                  <Field label="CPU quota" type="number" value={organizationDraft.cpu_quota} onChange={(value) => setOrganizationDraft({ ...organizationDraft, cpu_quota: value })} />
                  <Field label="Memory quota" type="number" value={organizationDraft.memory_quota} onChange={(value) => setOrganizationDraft({ ...organizationDraft, memory_quota: value })} />
                  <Field label="Budget quota" type="number" value={organizationDraft.budget_quota} onChange={(value) => setOrganizationDraft({ ...organizationDraft, budget_quota: value })} />
                  <button onClick={handleCreateOrganization} className="self-end rounded-md bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950">
                    Provision workspace
                  </button>
                </div>
              </section>
            ) : null}

            {auth.user.role === 'platform_admin' ? (
              <section className="mt-8 rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <h2 className="text-lg font-semibold text-slate-50">Provisioned organizations</h2>
                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="text-slate-400">
                      <tr>
                        <th className="pb-3 pr-4">Organization</th>
                        <th className="pb-3 pr-4">CPU quota</th>
                        <th className="pb-3 pr-4">Memory quota</th>
                        <th className="pb-3 pr-4">Budget quota</th>
                        <th className="pb-3 pr-4">Users</th>
                        <th className="pb-3">Experiments</th>
                      </tr>
                    </thead>
                    <tbody>
                      {organizations.map((organization) => (
                        <tr key={organization.id} className="border-t border-slate-800">
                          <td className="py-3 pr-4 text-slate-100">{organization.name}</td>
                          <td className="py-3 pr-4 text-slate-300">{organization.cpu_quota}</td>
                          <td className="py-3 pr-4 text-slate-300">{organization.memory_quota}</td>
                          <td className="py-3 pr-4 text-slate-300">{organization.budget_quota}</td>
                          <td className="py-3 pr-4 text-slate-300">{organization.user_count}</td>
                          <td className="py-3 text-slate-300">{organization.experiment_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}

            <section className="mt-8 rounded-xl border border-slate-800 bg-slate-900/70 p-5">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-50">Planning insight</h2>
                <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-amber-300">
                  {bestPolicy ? bestPolicy.policy : 'N/A'}
                </span>
              </div>
              <p className="text-sm text-slate-300">
                {bestPolicy
                  ? `${bestPolicy.policy.toUpperCase()} is currently the most effective strategy for this queue, balancing throughput, dependency cadence, and deadline risk with a score of ${bestPolicy.score.toFixed(1)}.`
                  : 'No eligible scheduling data is available yet.'}
              </p>
            </section>
          </>
        )}
      </div>
    </main>
  );
}

function StatCard({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string | number; tone: string }) {
  const toneStyles: Record<string, string> = {
    amber: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    sky: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
    violet: 'border-violet-500/30 bg-violet-500/10 text-violet-200',
    red: 'border-red-500/30 bg-red-500/10 text-red-200',
    emerald: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  };

  return (
    <div className={`rounded-xl border p-4 ${toneStyles[tone]}`}>
      <div className="mb-3 flex items-center justify-between text-slate-200">
        {icon}
        <BarChart3 className="h-4 w-4 text-white/50" />
      </div>
      <div className="text-2xl font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-300">{label}</div>
    </div>
  );
}

function InsightCard({ title, value, detail, accent }: { title: string; value: string; detail: string; accent: 'amber' | 'sky' | 'violet' }) {
  const accentStyles: Record<string, string> = {
    amber: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    sky: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
    violet: 'border-violet-500/30 bg-violet-500/10 text-violet-200',
  };

  return (
    <div className={`rounded-xl border p-4 ${accentStyles[accent]}`}>
      <div className="text-[10px] uppercase tracking-[0.20em] text-slate-300">{title}</div>
      <div className="mt-3 text-2xl font-semibold text-white">{value}</div>
      <div className="mt-1 text-sm text-slate-200">{detail}</div>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text' }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-[0.18em] text-slate-400">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-[0.18em] text-slate-400">{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-50"
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>{optionLabel}</option>
        ))}
      </select>
    </label>
  );
}

function StatusPill({ status }: { status: string }) {
  const statusMap: Record<string, string> = {
    ready: 'bg-emerald-500/15 text-emerald-300',
    queued: 'bg-blue-500/15 text-blue-300',
    running: 'bg-amber-500/15 text-amber-300',
    completed: 'bg-slate-500/15 text-slate-200',
    failed: 'bg-red-500/15 text-red-300',
    online: 'bg-emerald-500/15 text-emerald-300',
  };
  return <span className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${statusMap[status] || 'bg-slate-800 text-slate-300'}`}>{status}</span>;
}
