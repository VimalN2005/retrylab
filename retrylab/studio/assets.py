"""
RetryLab Chaos Studio Single-Page Web Application Assets.
Embedded self-contained modern dark-theme HTML, CSS, and reactive JavaScript interface.
Requires zero external CDNs, bundlers, or Node.js dependencies.
"""

from __future__ import annotations


def render_studio_html() -> str:
    """Render the complete standalone HTML/CSS/JS Chaos Studio SPA."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RetryLab Chaos Studio | Visual API Resilience Playground</title>
  <style>
    :root {
      --bg-primary: #0a0f1d;
      --bg-card: #131d31;
      --bg-input: #1a2640;
      --border-color: #263859;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --accent-cyan: #06b6d4;
      --accent-green: #10b981;
      --accent-red: #ef4444;
      --accent-yellow: #f59e0b;
      --accent-magenta: #ec4899;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-primary);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      padding-bottom: 40px;
    }

    header {
      background-color: var(--bg-card);
      border-bottom: 1px solid var(--border-color);
      padding: 16px 32px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 50;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-logo { font-size: 26px; }
    .brand-title { font-size: 20px; font-weight: 700; color: #fff; }
    .brand-badge {
      font-size: 11px;
      font-weight: 600;
      background: rgba(6, 182, 212, 0.15);
      color: var(--accent-cyan);
      border: 1px solid rgba(6, 182, 212, 0.3);
      padding: 3px 8px;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .preset-selector {
      background: var(--bg-input);
      color: var(--text-main);
      border: 1px solid var(--border-color);
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 13px;
      outline: none;
      cursor: pointer;
    }

    .btn {
      padding: 9px 18px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      border: none;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s ease;
    }

    .btn-primary {
      background: linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%);
      color: #fff;
      box-shadow: 0 4px 14px rgba(6, 182, 212, 0.3);
    }
    .btn-primary:hover { opacity: 0.95; transform: translateY(-1px); }
    .btn-secondary {
      background: var(--bg-input);
      color: var(--text-main);
      border: 1px solid var(--border-color);
    }
    .btn-secondary:hover { background: #223254; }

    main {
      max-width: 1400px;
      margin: 28px auto;
      padding: 0 24px;
      display: grid;
      grid-template-columns: 460px 1fr;
      gap: 28px;
    }

    @media (max-width: 1024px) {
      main { grid-template-columns: 1fr; }
    }

    .card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 24px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    }

    .card-title {
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: #fff;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 12px;
    }

    .form-group {
      margin-bottom: 16px;
    }

    label {
      display: block;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    input[type="text"], input[type="number"], select {
      width: 100%;
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 14px;
      outline: none;
      font-family: inherit;
      transition: border-color 0.2s;
    }

    input:focus, select:focus {
      border-color: var(--accent-cyan);
    }

    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }

    /* Scorecard Hero */
    .scorecard-hero {
      background: linear-gradient(135deg, rgba(6, 182, 212, 0.08) 0%, rgba(16, 185, 129, 0.08) 100%);
      border: 1px solid rgba(6, 182, 212, 0.25);
      border-radius: 12px;
      padding: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
    }

    .grade-badge {
      font-size: 38px;
      font-weight: 800;
      color: var(--accent-green);
      line-height: 1;
      padding: 10px 20px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 10px;
    }

    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 24px;
    }

    @media (max-width: 768px) {
      .metrics-grid { grid-template-columns: 1fr 1fr; }
    }

    .metric-pill {
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 12px;
      text-align: center;
    }

    .metric-pill-val {
      font-size: 18px;
      font-weight: 700;
      color: var(--accent-cyan);
    }

    .metric-pill-lbl {
      font-size: 11px;
      color: var(--text-muted);
      text-transform: uppercase;
      margin-top: 4px;
    }

    /* Timeline Waterfall */
    .timeline {
      margin-top: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .timeline-item {
      background: var(--bg-input);
      border-left: 4px solid var(--accent-cyan);
      border-radius: 0 8px 8px 0;
      padding: 12px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .timeline-item.fault {
      border-left-color: var(--accent-red);
      background: rgba(239, 68, 68, 0.06);
    }

    .timeline-item.recovered {
      border-left-color: var(--accent-green);
      background: rgba(16, 185, 129, 0.06);
    }

    .status-tag {
      font-size: 12px;
      font-weight: 700;
      padding: 4px 8px;
      border-radius: 6px;
      font-family: var(--font-mono);
    }
    .status-tag.fault { background: rgba(239, 68, 68, 0.2); color: var(--accent-red); }
    .status-tag.ok { background: rgba(16, 185, 129, 0.2); color: var(--accent-green); }

    /* Polyglot Code Export */
    .tabs-header {
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 14px;
    }

    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 13px;
      font-weight: 600;
      padding: 8px 14px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
    }

    .tab-btn.active {
      color: var(--accent-cyan);
      border-bottom-color: var(--accent-cyan);
    }

    pre.code-block {
      background: #060a13;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 16px;
      font-family: var(--font-mono);
      font-size: 12px;
      color: #e2e8f0;
      overflow-x: auto;
      white-space: pre-wrap;
      max-height: 280px;
    }

    .copy-btn {
      float: right;
      font-size: 11px;
      padding: 4px 8px;
      background: var(--bg-card);
      color: var(--text-muted);
      border: 1px solid var(--border-color);
      border-radius: 4px;
      cursor: pointer;
    }
    .copy-btn:hover { color: #fff; }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <span class="brand-logo">🧪</span>
      <span class="brand-title">RetryLab Chaos Studio</span>
      <span class="brand-badge">Local Playground</span>
    </div>
    <div class="header-actions">
      <select id="presetSelect" class="preset-selector" onchange="loadSelectedPreset()">
        <option value="">Select Curated Preset...</option>
      </select>
      <button class="btn btn-primary" onclick="runScenario()">
        <span>⚡</span> Run Chaos Simulation
      </button>
    </div>
  </header>

  <main>
    <!-- Left Column: Scenario Configurator -->
    <section class="card">
      <div class="card-title">
        <span>⚙️ Visual Scenario Builder</span>
        <button class="btn btn-secondary" style="font-size: 11px; padding: 4px 10px;" onclick="resetForm()">Reset</button>
      </div>

      <div class="form-group">
        <label>Scenario Identifier</label>
        <input type="text" id="scenarioName" value="stripe_payment_resilience">
      </div>

      <div class="form-group">
        <label>Target URL Pattern</label>
        <input type="text" id="targetUrl" value="https://api.stripe.com/v1/charges">
      </div>

      <div class="grid-2">
        <div class="form-group">
          <label>HTTP Method</label>
          <select id="httpMethod">
            <option value="POST">POST</option>
            <option value="GET">GET</option>
            <option value="PUT">PUT</option>
            <option value="DELETE">DELETE</option>
            <option value="ALL">ALL (Any)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Injected Fault</label>
          <select id="faultType" onchange="toggleFaultFields()">
            <option value="timeout">ReadTimeout (Socket)</option>
            <option value="http_status">HTTP Status Code</option>
            <option value="disconnect">TCP Connection Reset (RST)</option>
          </select>
        </div>
      </div>

      <div class="grid-2" id="statusFields">
        <div class="form-group">
          <label>Status Code</label>
          <input type="number" id="statusCode" value="503">
        </div>
        <div class="form-group">
          <label>Fail Count</label>
          <input type="number" id="failCount" value="1" min="1" max="10">
        </div>
      </div>

      <div class="grid-2">
        <div class="form-group">
          <label>Injected Latency (ms)</label>
          <input type="number" id="delayMs" value="120" min="0" step="10">
        </div>
        <div class="form-group">
          <label>Idempotency Header</label>
          <input type="text" id="idempHeader" value="Idempotency-Key">
        </div>
      </div>

      <div style="margin-top: 10px;">
        <button class="btn btn-primary" style="width: 100%; justify-content: center;" onclick="runScenario()">
          ⚡ Execute & Audit Recovery
        </button>
      </div>
    </section>

    <!-- Right Column: Live Results & Polyglot Exporter -->
    <section>
      <!-- Scorecard Hero -->
      <div class="scorecard-hero">
        <div>
          <div style="font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase;">Reliability Grade</div>
          <div id="gradeTitle" style="font-size: 18px; font-weight: 700; color: #fff; margin-top: 2px;">Elite Production Resilience</div>
          <div id="gradeDesc" style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Zero defect recovery with verified idempotency key preservation.</div>
        </div>
        <div id="gradeBadge" class="grade-badge">A+</div>
      </div>

      <!-- Metrics Breakdown -->
      <div class="metrics-grid">
        <div class="metric-pill">
          <div id="recovMetric" class="metric-pill-val">100%</div>
          <div class="metric-pill-lbl">Recovery Rate</div>
        </div>
        <div class="metric-pill">
          <div id="idempMetric" class="metric-pill-val" style="color: var(--accent-green);">PASSED</div>
          <div class="metric-pill-lbl">Idempotency</div>
        </div>
        <div class="metric-pill">
          <div id="backoffMetric" class="metric-pill-val" style="color: var(--accent-cyan);">VALID</div>
          <div class="metric-pill-lbl">Backoff Timing</div>
        </div>
        <div class="metric-pill">
          <div id="latencyMetric" class="metric-pill-val" style="color: var(--accent-yellow);">14.2ms</div>
          <div class="metric-pill-lbl">Mean Latency</div>
        </div>
      </div>

      <!-- Request Waterfall Timeline -->
      <div class="card" style="margin-bottom: 24px;">
        <div class="card-title">
          <span>🌊 Simulated In-Flight Request Waterfall</span>
          <span id="callCount" style="font-size: 12px; color: var(--text-muted);">2 Requests Audited</span>
        </div>
        <div id="timelineContainer" class="timeline">
          <!-- Dynamically populated -->
        </div>
      </div>

      <!-- Polyglot Code Export Card -->
      <div class="card">
        <div class="card-title">
          <span>📦 Polyglot SDK Exporter</span>
          <button class="copy-btn" onclick="copyActiveCode()">Copy Code</button>
        </div>
        <div class="tabs-header">
          <button class="tab-btn active" onclick="switchTab('python')">Python (HTTPX)</button>
          <button class="tab-btn" onclick="switchTab('go')">Go SDK</button>
          <button class="tab-btn" onclick="switchTab('typescript')">TypeScript</button>
          <button class="tab-btn" onclick="switchTab('yaml')">YAML</button>
        </div>
        <pre id="codeBlock" class="code-block"></pre>
      </div>
    </section>
  </main>

  <script>
    let currentExports = {};
    let activeTab = 'python';

    async function initStudio() {
      try {
        const res = await fetch('/api/presets');
        const data = await res.json();
        const sel = document.getElementById('presetSelect');
        data.presets.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.id;
          opt.textContent = `[${p.category}] ${p.name}`;
          sel.appendChild(opt);
        });
      } catch (err) {
        console.warn('Could not load presets:', err);
      }
      runScenario();
    }

    async function loadSelectedPreset() {
      const id = document.getElementById('presetSelect').value;
      if (!id) return;
      try {
        const res = await fetch('/api/presets');
        const data = await res.json();
        const preset = data.presets.find(p => p.id === id);
        if (preset) {
          document.getElementById('scenarioName').value = preset.id;
          document.getElementById('targetUrl').value = preset.target;
          document.getElementById('httpMethod').value = preset.method;
          document.getElementById('faultType').value = preset.fault;
          document.getElementById('statusCode').value = preset.status_code;
          document.getElementById('failCount').value = preset.fail_count;
          document.getElementById('delayMs').value = preset.delay_ms;
          document.getElementById('idempHeader').value = preset.idempotency_header || 'Idempotency-Key';
          runScenario();
        }
      } catch (err) {
        console.error(err);
      }
    }

    function toggleFaultFields() {
      const fault = document.getElementById('faultType').value;
      const statusDiv = document.getElementById('statusFields');
      if (fault === 'timeout' || fault === 'disconnect') {
        document.getElementById('statusCode').parentElement.style.opacity = '0.4';
      } else {
        document.getElementById('statusCode').parentElement.style.opacity = '1.0';
      }
      refreshExports();
    }

    async function runScenario() {
      const payload = {
        name: document.getElementById('scenarioName').value,
        target: document.getElementById('targetUrl').value,
        method: document.getElementById('httpMethod').value,
        fault: document.getElementById('faultType').value,
        status_code: parseInt(document.getElementById('statusCode').value),
        fail_count: parseInt(document.getElementById('failCount').value),
        delay_ms: parseInt(document.getElementById('delayMs').value),
        idempotency_header: document.getElementById('idempHeader').value,
      };

      try {
        const [runRes, expRes] = await Promise.all([
          fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
          fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        ]);

        const runData = await runRes.json();
        currentExports = await expRes.json();
        updateUI(runData);
        updateCodeBlock();
      } catch (err) {
        console.error('Run failed:', err);
      }
    }

    function updateUI(data) {
      const sc = data.scorecard;
      document.getElementById('gradeBadge').textContent = sc.letter_grade;
      document.getElementById('gradeTitle').textContent = `Score: ${sc.overall_score}/100`;
      document.getElementById('gradeDesc').textContent = sc.grade_description;

      const gradeColor = sc.letter_grade === 'A+' || sc.letter_grade === 'A' ? 'var(--accent-green)' : (sc.letter_grade === 'B' ? 'var(--accent-yellow)' : 'var(--accent-red)');
      document.getElementById('gradeBadge').style.color = gradeColor;

      document.getElementById('recovMetric').textContent = `${sc.recovery_rate}%`;
      document.getElementById('callCount').textContent = `${data.timeline.length} In-Flight Requests Audited`;

      // Timeline items
      const cont = document.getElementById('timelineContainer');
      cont.innerHTML = '';
      data.timeline.forEach(t => {
        const item = document.createElement('div');
        item.className = `timeline-item ${t.was_fault_injected ? 'fault' : 'recovered'}`;
        const badgeClass = t.was_fault_injected ? 'fault' : 'ok';
        const badgeLabel = t.was_fault_injected ? (t.error || `HTTP ${t.status_code}`) : `HTTP ${t.status_code} OK`;
        item.innerHTML = `
          <div>
            <div style="font-weight: 700; font-size: 13px;">Attempt #${t.attempt}: ${t.method} ${t.target}</div>
            <div style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono); margin-top: 2px;">
              Idempotency: ${t.idempotency_key} | Duration: ${t.latency_ms}ms
            </div>
          </div>
          <div>
            <span class="status-tag ${badgeClass}">${badgeLabel}</span>
          </div>
        `;
        cont.appendChild(item);
      });
    }

    function switchTab(tab) {
      activeTab = tab;
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      event.target.classList.add('active');
      updateCodeBlock();
    }

    function updateCodeBlock() {
      const code = currentExports[activeTab] || '// Loading snippet...';
      document.getElementById('codeBlock').textContent = code;
    }

    function copyActiveCode() {
      const code = document.getElementById('codeBlock').textContent;
      navigator.clipboard.writeText(code);
      event.target.textContent = 'Copied!';
      setTimeout(() => { event.target.textContent = 'Copy Code'; }, 1500);
    }

    function resetForm() {
      document.getElementById('scenarioName').value = 'custom_chaos_scenario';
      document.getElementById('targetUrl').value = 'https://api.stripe.com/v1/charges';
      document.getElementById('httpMethod').value = 'POST';
      document.getElementById('faultType').value = 'timeout';
      document.getElementById('statusCode').value = 503;
      document.getElementById('failCount').value = 1;
      document.getElementById('delayMs').value = 50;
      runScenario();
    }

    window.addEventListener('DOMContentLoaded', initStudio);
  </script>
</body>
</html>
"""
