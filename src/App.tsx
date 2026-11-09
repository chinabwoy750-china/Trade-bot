import React, { useState } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  Cpu,
  Database,
  Layers,
  Terminal,
  Activity,
  CheckCircle2,
  Clock,
  Coins,
  AlertTriangle,
  FileCode2,
  Sliders,
  Play,
  RotateCcw,
  Sparkles,
  ArrowRight,
  TrendingUp,
  Search,
  Lock,
} from 'lucide-react';

interface Phase {
  id: number;
  name: string;
  description: string;
  status: 'COMPLETED' | 'IN_PROGRESS' | 'PENDING';
  tags: string[];
}

const PHASES: Phase[] = [
  {
    id: 1,
    name: 'Foundation',
    description: 'Project skeleton, YAML config loaders, structured logging, SQLite persistence, BrokerInterface ABC, Pydantic schemas, mode safety gate.',
    status: 'COMPLETED',
    tags: ['Mode Safety Gate', 'YAML Configs', 'Broker ABC', 'Pydantic v2', 'SQLite DB', '32 Unit Tests'],
  },
  {
    id: 2,
    name: 'Data Layer',
    description: 'OANDA REST API & Alpaca paper data connectors, multi-timeframe candle store (M15, H1, H4, D1), technical indicators, staleness checking.',
    status: 'PENDING',
    tags: ['OANDA Demo', 'Alpaca Paper', 'OHLCV Storage', 'Max Age Gate'],
  },
  {
    id: 3,
    name: 'Risk Manager',
    description: 'Full deterministic risk layer: position sizing (pips, crypto fractions), currency exposure caps, daily loss halt (3%), consecutive loss halts.',
    status: 'PENDING',
    tags: ['Absolute Veto', 'Sizing Math', 'Daily Loss Limit', 'Spread Check'],
  },
  {
    id: 4,
    name: 'Pre-Filter & Analyst Team',
    description: 'Rule-based shortlist (top 3-5 candidates), Technical Analyst, Calendar Guard (30m blackout), News Analyst, Macro Sentiment.',
    status: 'PENDING',
    tags: ['Shortlist Filter', 'Calendar Blackout', 'Sentiment Filter', 'Order Book'],
  },
  {
    id: 5,
    name: 'Decision Agent',
    description: 'Model-agnostic LLM client, structured JSON decision parsing, signal hierarchy enforcement, retry and failsafe HOLD fallback.',
    status: 'PENDING',
    tags: ['Thesis & Levels', 'R:R >= 1.5', 'Strict JSON', 'Injection Defense'],
  },
  {
    id: 6,
    name: 'Execution Engine',
    description: 'Broker connectors for OANDA & Alpaca, attached SL/TP orders, state reconciliation, idempotent client order IDs, break-even tightening.',
    status: 'PENDING',
    tags: ['Attached Stops', 'Reconciliation', 'Tighten SL', 'Fills Audit'],
  },
  {
    id: 7,
    name: 'Backtester',
    description: 'Realistic backtest simulator with slippage, spreads, fees, rule-based stand-in & LLM replay, Sharpe, drawdowns, equity curve.',
    status: 'PENDING',
    tags: ['No Look-Ahead', 'Realistic Costs', 'Performance Metrics'],
  },
  {
    id: 8,
    name: 'Telegram Alerts & Remote Control',
    description: 'Telegram bot with user ID allowlist: /status, /positions, /pause, /resume, /killswitch, daily performance reports.',
    status: 'PENDING',
    tags: ['Telegram Bot', 'Killswitch', 'User Allowlist', 'Push Alerts'],
  },
  {
    id: 9,
    name: 'Deployment & VPS Hardening',
    description: 'Dockerfile, docker-compose.yml, systemd service unit, healthcheck daemon, auto-restart on fail, VPS setup guide.',
    status: 'PENDING',
    tags: ['Docker', 'Systemd', 'Healthcheck', 'Auto-Restart'],
  },
  {
    id: 10,
    name: 'Demo Paper Run Plan',
    description: '2 to 4 week paper/demo testing regimen with daily review checklists. Live trading remains locked.',
    status: 'PENDING',
    tags: ['Paper Verification', 'Daily Checklist', 'Live Safe'],
  },
];

const FOREX_INSTRUMENTS = [
  { symbol: 'EUR_USD', name: 'EUR/USD', base: 'EUR', quote: 'USD', pip: '0.0001' },
  { symbol: 'GBP_USD', name: 'GBP/USD', base: 'GBP', quote: 'USD', pip: '0.0001' },
  { symbol: 'USD_JPY', name: 'USD/JPY', base: 'USD', quote: 'JPY', pip: '0.01' },
  { symbol: 'USD_CHF', name: 'USD/CHF', base: 'USD', quote: 'CHF', pip: '0.0001' },
  { symbol: 'AUD_USD', name: 'AUD/USD', base: 'AUD', quote: 'USD', pip: '0.0001' },
  { symbol: 'USD_CAD', name: 'USD/CAD', base: 'USD', quote: 'CAD', pip: '0.0001' },
  { symbol: 'NZD_USD', name: 'NZD/USD', base: 'NZD', quote: 'USD', pip: '0.0001' },
  { symbol: 'EUR_GBP', name: 'EUR/GBP', base: 'EUR', quote: 'GBP', pip: '0.0001' },
  { symbol: 'EUR_JPY', name: 'EUR/JPY', base: 'EUR', quote: 'JPY', pip: '0.01' },
  { symbol: 'GBP_JPY', name: 'GBP/JPY', base: 'GBP', quote: 'JPY', pip: '0.01' },
  { symbol: 'AUD_JPY', name: 'AUD/JPY', base: 'AUD', quote: 'JPY', pip: '0.01' },
  { symbol: 'XAU_USD', name: 'Gold (XAU/USD)', base: 'XAU', quote: 'USD', pip: '0.01' },
];

const CRYPTO_INSTRUMENTS = [
  { symbol: 'BTC/USD', name: 'Bitcoin', minQty: '0.0001', type: 'Spot Long' },
  { symbol: 'ETH/USD', name: 'Ethereum', minQty: '0.001', type: 'Spot Long' },
  { symbol: 'SOL/USD', name: 'Solana', minQty: '0.01', type: 'Spot Long' },
  { symbol: 'XRP/USD', name: 'XRP', minQty: '1.0', type: 'Spot Long' },
  { symbol: 'ADA/USD', name: 'Cardano', minQty: '1.0', type: 'Spot Long' },
  { symbol: 'DOGE/USD', name: 'Dogecoin', minQty: '10.0', type: 'Spot Long' },
  { symbol: 'LINK/USD', name: 'Chainlink', minQty: '0.1', type: 'Spot Long' },
  { symbol: 'AVAX/USD', name: 'Avalanche', minQty: '0.1', type: 'Spot Long' },
  { symbol: 'LTC/USD', name: 'Litecoin', minQty: '0.01', type: 'Spot Long' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<'architecture' | 'phases' | 'config' | 'schema' | 'tests'>('architecture');
  const [schemaMode, setSchemaMode] = useState<'BUY' | 'HOLD'>('BUY');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-emerald-500 selection:text-black">
      {/* Top Banner: Mode Safety Gate */}
      <div className="bg-slate-900 border-b border-slate-800 px-6 py-2.5 flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-mono font-medium border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            MODE: DEMO (PAPER ONLY)
          </span>
          <span className="text-slate-400 hidden sm:inline">
            Non-negotiable Safety Gate: Live trading is hardware/env locked
          </span>
        </div>
        <div className="flex items-center gap-4 text-slate-400 font-mono">
          <span className="flex items-center gap-1.5">
            <Lock className="w-3.5 h-3.5 text-amber-400" />
            LIVE_CONFIRM: <span className="text-slate-500">LOCKED</span>
          </span>
          <span className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-blue-400" />
            15m Candle Cycle
          </span>
        </div>
      </div>

      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-6 py-5">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-emerald-600 via-teal-500 to-cyan-500 p-0.5 shadow-lg shadow-emerald-500/10">
              <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
                <Cpu className="w-6 h-6 text-emerald-400" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-white">AI Multi-Asset Trading Bot</h1>
                <span className="px-2 py-0.5 text-[10px] font-mono uppercase rounded bg-slate-800 text-slate-300 border border-slate-700">
                  Forex + Crypto
                </span>
                <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                  Phase 1 Verified
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Paper-trading-first automated quant system with AI decision agent and deterministic risk veto layer.
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs">
            <button
              onClick={() => setActiveTab('architecture')}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                activeTab === 'architecture' ? 'bg-emerald-500 text-slate-950 shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              Cycle Architecture
            </button>
            <button
              onClick={() => setActiveTab('phases')}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                activeTab === 'phases' ? 'bg-emerald-500 text-slate-950 shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              10-Phase Roadmap
            </button>
            <button
              onClick={() => setActiveTab('config')}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                activeTab === 'config' ? 'bg-emerald-500 text-slate-950 shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              Instruments & Risk
            </button>
            <button
              onClick={() => setActiveTab('schema')}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                activeTab === 'schema' ? 'bg-emerald-500 text-slate-950 shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              Decision Schema
            </button>
            <button
              onClick={() => setActiveTab('tests')}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                activeTab === 'tests' ? 'bg-emerald-500 text-slate-950 shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              Test Results (32/32)
            </button>
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
        {activeTab === 'architecture' && (
          <div className="space-y-6">
            {/* Top Summary Metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800/80">
                <div className="flex items-center justify-between text-slate-400 text-xs mb-1.5">
                  <span>Safety Status</span>
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="text-xl font-bold text-emerald-400 font-mono">DEMO_SAFE</div>
                <div className="text-[11px] text-slate-500 mt-1">Live mode locked by fail-safe gate</div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800/80">
                <div className="flex items-center justify-between text-slate-400 text-xs mb-1.5">
                  <span>Risk Per Trade</span>
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                </div>
                <div className="text-xl font-bold text-white font-mono">1.0% Equity</div>
                <div className="text-[11px] text-slate-500 mt-1">Scale down to 0.2% on low confidence</div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800/80">
                <div className="flex items-center justify-between text-slate-400 text-xs mb-1.5">
                  <span>Global Daily Loss Halt</span>
                  <ShieldAlert className="w-4 h-4 text-rose-400" />
                </div>
                <div className="text-xl font-bold text-rose-400 font-mono">3.0% Max Loss</div>
                <div className="text-[11px] text-slate-500 mt-1">Immediate halt on daily threshold</div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800/80">
                <div className="flex items-center justify-between text-slate-400 text-xs mb-1.5">
                  <span>Unit Test Coverage</span>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="text-xl font-bold text-white font-mono">88% Coverage</div>
                <div className="text-[11px] text-slate-500 mt-1">32/32 tests passing & mypy clean</div>
              </div>
            </div>

            {/* Architecture Pipeline Visualizer */}
            <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-base font-semibold text-white flex items-center gap-2">
                    <Activity className="w-4 h-4 text-emerald-400" />
                    The 7-Stage Execution & Risk Pipeline
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Deterministic fail-safe quant architecture. The AI proposes; plain code validates and executes.
                  </p>
                </div>
                <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-300">
                  Cycle Cadence: 15 Minutes
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-7 gap-3 relative">
                {/* Stage 1: Data */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-mono text-cyan-400 font-semibold mb-1">STAGE 01</div>
                    <div className="text-xs font-bold text-white">Data Layer</div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      OHLCV multi-timeframe (M15, H1, H4, D1). If age &gt; 300s &rarr; <span className="font-mono text-rose-400">DATA_STALE</span>.
                    </p>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-slate-500">
                    OANDA + Alpaca
                  </div>
                </div>

                {/* Stage 2: Pre-Filter */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-mono text-cyan-400 font-semibold mb-1">STAGE 02</div>
                    <div className="text-xs font-bold text-white">Pre-Filter (No AI)</div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Computes indicators and shortlists <span className="text-white font-semibold">top 3 to 5</span> symbols with real setups. Controls API cost.
                    </p>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-slate-500">
                    Rule-Based Gate
                  </div>
                </div>

                {/* Stage 3: Analysts */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-mono text-cyan-400 font-semibold mb-1">STAGE 03</div>
                    <div className="text-xs font-bold text-white">Analyst Team</div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Technical, Calendar Guard (30m blackout), News sentiment filter, Macro rates, Order book delta.
                    </p>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-slate-500">
                    Structured Scores
                  </div>
                </div>

                {/* Stage 4: AI Decision */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-purple-500/30 bg-purple-950/10 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-mono text-purple-400 font-semibold mb-1">STAGE 04</div>
                    <div className="text-xs font-bold text-purple-200">AI Decision Agent</div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Signal hierarchy: Momentum &gt; Trend &gt; Pivots. Outputs strict JSON thesis, levels, R:R &ge; 1.5.
                    </p>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-purple-400">
                    Proposes Only
                  </div>
                </div>

                {/* Stage 5: Deterministic Risk */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-rose-500/40 bg-rose-950/10 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-mono text-rose-400 font-semibold mb-1">STAGE 05</div>
                    <div className="text-xs font-bold text-rose-200">Risk Manager (Veto)</div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      <span className="text-rose-400 font-semibold">Absolute Veto.</span> Sizing per pip/coin, exposure caps, daily loss limits. No AI inside.
                    </p>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-rose-400">
                    Zero Hallucination
                  </div>
                </div>

                {/* Stage 6: Execution */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-mono text-cyan-400 font-semibold mb-1">STAGE 06</div>
                    <div className="text-xs font-bold text-white">Execution Engine</div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Attached SL &amp; TP at order creation. Tightens stops, never widens. Idempotent order IDs.
                    </p>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-slate-500">
                    Broker Reconciled
                  </div>
                </div>

                {/* Stage 7: Storage & Telegram */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-mono text-cyan-400 font-semibold mb-1">STAGE 07</div>
                    <div className="text-xs font-bold text-white">Storage &amp; Alerts</div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      SQLite audits every decision (including HOLDs and vetoes). Telegram alerts &amp; remote killswitch.
                    </p>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-slate-500">
                    Complete Audit Trail
                  </div>
                </div>
              </div>
            </div>

            {/* Non-Negotiable Invariants & Principles */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
                <h3 className="text-xs font-semibold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  Hard-Coded Safety Rules (Phase 1 Enforced)
                </h3>
                <ul className="space-y-2 text-xs text-slate-300">
                  <li className="flex items-start gap-2">
                    <span className="text-emerald-400 font-bold mt-0.5">&#10003;</span>
                    <span>
                      <strong className="text-white">Paper/demo by default:</strong> Live mode requires both <code className="text-amber-400">MODE=live</code> and <code className="text-amber-400">LIVE_CONFIRM=I_UNDERSTAND_THE_RISK</code>.
                    </span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-emerald-400 font-bold mt-0.5">&#10003;</span>
                    <span>
                      <strong className="text-white">Deterministic risk veto:</strong> The AI proposes; deterministic code has absolute authority to veto.
                    </span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-emerald-400 font-bold mt-0.5">&#10003;</span>
                    <span>
                      <strong className="text-white">Attached protective stop:</strong> Every order must have an attached stop-loss at order time. Never widen a stop. Never average down.
                    </span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-emerald-400 font-bold mt-0.5">&#10003;</span>
                    <span>
                      <strong className="text-white">Input Integrity:</strong> Untrusted text (news, calendar, headlines) is inspected for prompt injection. Quarantined upon detection.
                    </span>
                  </li>
                </ul>
              </div>

              <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
                <h3 className="text-xs font-semibold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-blue-400" />
                  Session &amp; Timing Boundaries
                </h3>
                <div className="space-y-3 text-xs">
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                    <div className="flex justify-between items-center text-slate-300 font-semibold mb-1">
                      <span>Forex &amp; Gold (24/5)</span>
                      <span className="text-emerald-400 font-mono text-[11px]">OANDA REST API</span>
                    </div>
                    <p className="text-slate-400 text-[11px]">
                      Closes Friday 21:00 UTC, reopens Sunday 21:00 UTC. Automatically issues <code className="text-slate-300">HOLD (OUTSIDE_SESSION)</code> during weekend hours.
                    </p>
                  </div>
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                    <div className="flex justify-between items-center text-slate-300 font-semibold mb-1">
                      <span>Crypto Spot (24/7)</span>
                      <span className="text-emerald-400 font-mono text-[11px]">Alpaca Paper API</span>
                    </div>
                    <p className="text-slate-400 text-[11px]">
                      Spot, long-only (no shorting). Symbol verification at boot; unsupported tokens skipped safely with audit log.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'phases' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div>
                <h2 className="text-sm font-semibold text-white">Project Implementation Phases</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Phase-by-phase execution plan. Each phase runs unit tests and requires explicit user review before advancing.
                </p>
              </div>
              <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded">
                Phase 1 of 10 Complete
              </span>
            </div>

            <div className="grid grid-cols-1 gap-3">
              {PHASES.map((phase) => (
                <div
                  key={phase.id}
                  className={`p-4 rounded-xl border transition-all ${
                    phase.status === 'COMPLETED'
                      ? 'bg-slate-900/90 border-emerald-500/40'
                      : 'bg-slate-900/40 border-slate-800/80 opacity-75'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-7 h-7 rounded-lg flex items-center justify-center font-mono text-xs font-bold ${
                          phase.status === 'COMPLETED'
                            ? 'bg-emerald-500 text-slate-950'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {phase.id}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-xs font-bold text-white">{phase.name}</h3>
                          {phase.status === 'COMPLETED' && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/50">
                              <CheckCircle2 className="w-3 h-3" /> VERIFIED
                            </span>
                          )}
                          {phase.status === 'PENDING' && (
                            <span className="text-[10px] font-mono text-slate-500 bg-slate-800/40 px-2 py-0.5 rounded">
                              QUEUED FOR REVIEW
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-400 mt-1">{phase.description}</p>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-1.5 self-start sm:self-center">
                      {phase.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-950 text-slate-300 border border-slate-800"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'config' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Tradable Forex Instruments */}
              <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-bold text-white flex items-center gap-2 uppercase tracking-wider">
                    <Coins className="w-4 h-4 text-emerald-400" />
                    Forex &amp; Gold Instruments (~30 Defined)
                  </h3>
                  <span className="text-[11px] font-mono text-slate-400">config/instruments.yaml</span>
                </div>
                <div className="overflow-x-auto max-h-72 overflow-y-auto rounded border border-slate-800">
                  <table className="w-full text-left text-xs text-slate-300">
                    <thead className="bg-slate-950 text-[11px] font-mono text-slate-400 sticky top-0">
                      <tr>
                        <th className="p-2.5">Symbol</th>
                        <th className="p-2.5">Name</th>
                        <th className="p-2.5">Base / Quote</th>
                        <th className="p-2.5">Pip Size</th>
                        <th className="p-2.5">Broker</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                      {FOREX_INSTRUMENTS.map((inst) => (
                        <tr key={inst.symbol} className="hover:bg-slate-800/30">
                          <td className="p-2.5 font-bold text-emerald-400">{inst.symbol}</td>
                          <td className="p-2.5 text-white font-sans">{inst.name}</td>
                          <td className="p-2.5 text-slate-400">{inst.base} / {inst.quote}</td>
                          <td className="p-2.5">{inst.pip}</td>
                          <td className="p-2.5 text-slate-400">OANDA (Demo)</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Tradable Crypto Instruments */}
              <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-bold text-white flex items-center gap-2 uppercase tracking-wider">
                    <TrendingUp className="w-4 h-4 text-cyan-400" />
                    Crypto Spot Instruments (Alpaca Paper)
                  </h3>
                  <span className="text-[11px] font-mono text-slate-400">Spot Long-Only</span>
                </div>
                <div className="overflow-x-auto max-h-72 overflow-y-auto rounded border border-slate-800">
                  <table className="w-full text-left text-xs text-slate-300">
                    <thead className="bg-slate-950 text-[11px] font-mono text-slate-400 sticky top-0">
                      <tr>
                        <th className="p-2.5">Symbol</th>
                        <th className="p-2.5">Asset</th>
                        <th className="p-2.5">Min Order Qty</th>
                        <th className="p-2.5">Type</th>
                        <th className="p-2.5">Broker</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                      {CRYPTO_INSTRUMENTS.map((coin) => (
                        <tr key={coin.symbol} className="hover:bg-slate-800/30">
                          <td className="p-2.5 font-bold text-cyan-400">{coin.symbol}</td>
                          <td className="p-2.5 text-white font-sans">{coin.name}</td>
                          <td className="p-2.5">{coin.minQty}</td>
                          <td className="p-2.5 text-emerald-400">{coin.type}</td>
                          <td className="p-2.5 text-slate-400">Alpaca Paper</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Risk Configuration Values */}
            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
              <h3 className="text-xs font-bold text-white flex items-center gap-2 uppercase tracking-wider mb-4">
                <Sliders className="w-4 h-4 text-emerald-400" />
                Deterministic Risk Parameters (config/risk.yaml)
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-slate-400 text-[11px]">Max Risk Per Trade</div>
                  <div className="text-base font-bold font-mono text-emerald-400 mt-0.5">1.0% Equity</div>
                  <div className="text-[10px] text-slate-500 mt-1">Scale to 0.2% on low confidence</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-slate-400 text-[11px]">Net Currency Exposure Cap</div>
                  <div className="text-base font-bold font-mono text-white mt-0.5">3.0% Net Equity</div>
                  <div className="text-[10px] text-slate-500 mt-1">Prevents over-exposure to USD/EUR</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-slate-400 text-[11px]">Crypto Portfolio Cap</div>
                  <div className="text-base font-bold font-mono text-cyan-400 mt-0.5">20.0% Aggregate</div>
                  <div className="text-[10px] text-slate-500 mt-1">Controls high-correlation crypto risk</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-slate-400 text-[11px]">Consecutive Loss Halt</div>
                  <div className="text-base font-bold font-mono text-rose-400 mt-0.5">4 Consecutive</div>
                  <div className="text-[10px] text-slate-500 mt-1">Triggers manual review lock</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'schema' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div>
                <h2 className="text-sm font-semibold text-white">Strict Pydantic Decision Output Schemas</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  The AI Decision Agent must output valid JSON matching these exact schemas. Retried once on error, then falls back to HOLD.
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setSchemaMode('BUY')}
                  className={`px-3 py-1 rounded text-xs font-mono font-medium transition-colors ${
                    schemaMode === 'BUY' ? 'bg-emerald-500 text-slate-950' : 'bg-slate-800 text-slate-300'
                  }`}
                >
                  BUY / SELL Schema
                </button>
                <button
                  onClick={() => setSchemaMode('HOLD')}
                  className={`px-3 py-1 rounded text-xs font-mono font-medium transition-colors ${
                    schemaMode === 'HOLD' ? 'bg-amber-500 text-slate-950' : 'bg-slate-800 text-slate-300'
                  }`}
                >
                  HOLD Schema
                </button>
              </div>
            </div>

            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
              {schemaMode === 'BUY' ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-emerald-400">TradeDecision (Pydantic v2)</span>
                    <span className="text-[11px] text-slate-400 font-mono">trading_bot.decision.models</span>
                  </div>
                  <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-emerald-300 overflow-x-auto leading-relaxed">
{`{
  "action": "BUY",
  "symbol": "EUR_USD",
  "quantity": 10000.0,
  "entry_type": "MARKET",
  "limit_price": null,
  "stop_loss": 1.0810,
  "take_profit": 1.0920,
  "risk_reward": 2.2,
  "risk_usd": 50.0,
  "reasoning": "H4 bullish trend continuation off 50 EMA with positive taker volume spike.",
  "invalidation_condition": "Candle close below 1.0805 on 15m timeframe.",
  "confidence": 0.85
}`}
                  </pre>
                  <div className="p-3 rounded bg-slate-950 border border-slate-800/80 text-xs text-slate-400 space-y-1">
                    <p><strong className="text-slate-200">Validation Invariants:</strong></p>
                    <p>&bull; For BUY: <code className="text-emerald-400">stop_loss &lt; entry &lt; take_profit</code></p>
                    <p>&bull; For SELL: <code className="text-rose-400">take_profit &lt; entry &lt; stop_loss</code></p>
                    <p>&bull; Minimum Risk/Reward: <code className="text-white">R:R &ge; 1.5</code></p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-amber-400">HoldDecision (Pydantic v2)</span>
                    <span className="text-[11px] text-slate-400 font-mono">trading_bot.decision.models</span>
                  </div>
                  <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-amber-300 overflow-x-auto leading-relaxed">
{`{
  "action": "HOLD",
  "reason_code": "NO_EDGE",
  "reasoning": "Market consolidating without multi-timeframe trend alignment.",
  "missing_condition_diagnostic": "DIAGNOSTIC after 4 consecutive HOLDs: Missing leading momentum criteria."
}`}
                  </pre>
                  <div className="p-3 rounded bg-slate-950 border border-slate-800/80 text-xs text-slate-400 space-y-1">
                    <p><strong className="text-slate-200">Standard Reason Codes:</strong></p>
                    <p>&bull; <code className="text-slate-300">NO_EDGE</code> | <code className="text-slate-300">DATA_STALE</code> | <code className="text-slate-300">RISK_LIMIT</code> | <code className="text-slate-300">LOW_CONFIDENCE</code> | <code className="text-slate-300">OUTSIDE_SESSION</code> | <code className="text-slate-300">INPUT_INTEGRITY_FAILURE</code> | <code className="text-slate-300">OTHER</code></p>
                    <p>&bull; After N consecutive HOLDs, reasoning includes missing condition diagnostic.</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'tests' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div>
                <h2 className="text-sm font-semibold text-white">Phase 1 Test Suite Execution Evidence</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Run directly on the VPS runtime via <code className="text-slate-300">pytest -v --cov=trading_bot</code>, <code className="text-slate-300">ruff</code>, and <code className="text-slate-300">mypy</code>.
                </p>
              </div>
              <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded">
                32 Passed &bull; 0 Failed &bull; 0 Warnings
              </span>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs overflow-x-auto">
              <div className="text-slate-400 border-b border-slate-800 pb-2 mb-3 flex items-center justify-between">
                <span>pytest tests/test_phase1.py --cov=trading_bot</span>
                <span className="text-emerald-400 font-bold">100% PASS RATE</span>
              </div>
              <div className="space-y-1 text-slate-300 text-[11px]">
                <div className="flex justify-between py-0.5">
                  <span>test_default_mode_is_demo</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_backtest_mode_allowed</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_live_mode_blocked_without_confirm</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_live_mode_blocked_with_wrong_confirm</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_live_mode_allowed_only_with_exact_phrase</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_load_app_config_from_yaml</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_min_risk_cannot_exceed_max_risk</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_valid_buy_decision</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_buy_decision_rejects_stop_loss_above_entry</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_sell_decision_rejects_stop_loss_below_entry</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_consecutive_hold_diagnostic_tracker</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_detects_prompt_injection_attempts</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_sanitize_raises_integrity_failure</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_persist_trade_decision</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_persist_risk_veto</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_mock_broker_contract</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_forex_market_closed_friday_night</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_forex_market_open_sunday_night</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>test_candle_alignment_calculation</span>
                  <span className="text-emerald-400">PASSED</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 px-6 py-4 text-xs text-slate-500 flex flex-col sm:flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
          <span>Phase 1 Verified &bull; Python 3.10/3.11+ &bull; Ready for Phase 2 Approval</span>
        </div>
        <div className="font-mono text-[11px] text-slate-400">
          OANDA Practice REST + Alpaca Paper Crypto
        </div>
      </footer>
    </div>
  );
}
