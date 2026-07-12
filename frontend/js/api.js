const API_BASE_URL = localStorage.getItem("newsIntelligenceApiBaseUrl") || "";
const MOCK_MODE = false;

(function () {
  const ENDPOINTS = {
    analyse: "/news/analyse",
    events: "/news/events",
    eventDetail: (eventId) => `/news/events/${encodeURIComponent(eventId)}/detail`,
    clusters: (clusterId) => `/news/clusters/${encodeURIComponent(clusterId)}`,
    signals: (symbol) => `/news/signals/${encodeURIComponent(symbol)}`,
    recent: "/news/events/recent",
    sources: "/sources/status",
    sourceFilings: "/sources/filings/recent",
    secEdgarPoll: "/sources/sec-edgar/poll",
    worldNewsPoll: "/sources/world-news/poll",
    pollDueSources: "/sources/poll-due",
    automation: "/automation/status",
    automationRunNow: "/automation/run-now",
    universe: "/universe/favourites",
    calibration: "/calibration/report",
    calibrationOutcomes: "/calibration/outcomes",
    fileDropStatus: "/outputs/file-drop/status",
    fileDropLatest: "/outputs/file-drop/latest",
    marketBars: "/market-data/bars/recent",
    marketRequests: "/market-data/requests/recent",
    storageLayers: "/storage/layers",
    retentionDryRun: "/storage/retention/dry-run",
    retentionApply: "/storage/retention/apply",
    testRuns: "/test-runs",
    testRun: (testRunId) => `/test-runs/${encodeURIComponent(testRunId)}`,
    developmentData: "/development-data",
    health: "/health"
  };

  let simulateFailure = false;

  function useMockMode() {
    return MOCK_MODE || localStorage.getItem("newsIntelligenceMockMode") === "true";
  }

  async function request(path, options) {
    if (simulateFailure) {
      const error = new Error("Simulated backend failure");
      error.stage = "API";
      error.requestId = "simulated";
      throw error;
    }
    const response = await fetch(`${API_BASE_URL}${path}`, options);
    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (error) {
        payload = {detail: text};
      }
    }
    if (!response.ok) {
      const error = new Error(payload && payload.detail ? payload.detail : `HTTP ${response.status}`);
      error.stage = "API";
      error.requestId = response.headers.get("x-request-id") || "unavailable";
      error.detail = payload;
      throw error;
    }
    return payload;
  }

  async function analyse(payload) {
    if (useMockMode()) {
      if (simulateFailure) {
        const error = new Error("Simulated backend failure");
        error.stage = "Mock API";
        error.requestId = "simulated";
        throw error;
      }
      return window.NewsFixtures.mockAnalyse(payload);
    }
    return request(ENDPOINTS.analyse, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
  }

  async function recentEvents() {
    if (useMockMode()) {
      return [];
    }
    return request(ENDPOINTS.recent);
  }

  async function eventDetail(eventId) {
    if (useMockMode()) {
      throw new Error("Recent event reload is unavailable in mock mode until an event is analysed.");
    }
    return request(ENDPOINTS.eventDetail(eventId));
  }

  async function sourceStatus() {
    if (useMockMode()) {
      return window.NewsFixtures.mockSourceStatus();
    }
    return request(ENDPOINTS.sources);
  }

  async function sourceFilings() {
    if (useMockMode()) {
      return [];
    }
    return request(ENDPOINTS.sourceFilings);
  }

  async function pollSecEdgar(force) {
    if (useMockMode()) {
      return {source_name: "SEC EDGAR", ingested_count: 0, skipped_count: 0, filings: []};
    }
    const suffix = force ? "?force=true" : "";
    return request(`${ENDPOINTS.secEdgarPoll}${suffix}`, {method: "POST"});
  }

  async function pollWorldNews(force) {
    if (useMockMode()) {
      return {source_name: "World News Monitor", ingested_count: 0, skipped_count: 0, items: []};
    }
    const suffix = force ? "?force=true" : "";
    return request(`${ENDPOINTS.worldNewsPoll}${suffix}`, {method: "POST"});
  }

  async function pollDueSources(force) {
    if (useMockMode()) {
      return [];
    }
    const suffix = force ? "?force=true" : "";
    return request(`${ENDPOINTS.pollDueSources}${suffix}`, {method: "POST"});
  }

  async function automationStatus() {
    if (useMockMode()) {
      return {enabled: false, sources: [], stale_count: 0, due_count: 0};
    }
    return request(ENDPOINTS.automation);
  }

  async function automationRunNow(force) {
    if (useMockMode()) {
      return {
        automation_run_id: `mock_auto_${Date.now()}`,
        reason: "mock",
        source_run_count: 0,
        fetched_count: 0,
        ingested_count: 0,
        skipped_count: 0,
        error_count: 0,
        source_runs: []
      };
    }
    const suffix = force ? "?force=true" : "";
    return request(`${ENDPOINTS.automationRunNow}${suffix}`, {method: "POST"});
  }

  async function favouritesUniverse() {
    if (useMockMode()) {
      return {version: "mock", instruments: []};
    }
    return request(ENDPOINTS.universe);
  }

  async function calibrationReport() {
    if (useMockMode()) {
      return {profiles: [], signal_count: 0, outcome_status: "mock"};
    }
    return request(ENDPOINTS.calibration);
  }

  async function calibrationOutcomes() {
    if (useMockMode()) {
      return {rows: [], outcome_count: 0, missing_market_data_count: 0, outcome_status: "mock"};
    }
    return request(ENDPOINTS.calibrationOutcomes);
  }

  async function fileDropStatus() {
    if (useMockMode()) {
      return {enabled: false, output_dir: "mock"};
    }
    return request(ENDPOINTS.fileDropStatus);
  }

  async function marketBars() {
    if (useMockMode()) {
      return [];
    }
    return request(ENDPOINTS.marketBars);
  }

  async function marketRequests() {
    if (useMockMode()) {
      return [];
    }
    return request(ENDPOINTS.marketRequests);
  }

  async function storageLayers() {
    if (useMockMode()) {
      return {
        schema_version: "1.0.0",
        retention_version: "mock",
        generated_at: new Date().toISOString(),
        database_path: "mock",
        database_file_bytes: 0,
        total_current_bytes: 0,
        total_projected_bytes: 0,
        layers: []
      };
    }
    return request(ENDPOINTS.storageLayers);
  }

  async function storageRetentionDryRun(retentionDays) {
    if (useMockMode()) {
      return mockRetentionPlan("dry_run");
    }
    return request(ENDPOINTS.retentionDryRun, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({retention_days: retentionDays || {}})
    });
  }

  async function applyStorageRetention(retentionDays) {
    if (useMockMode()) {
      return mockRetentionPlan("applied");
    }
    return request(ENDPOINTS.retentionApply, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({retention_days: retentionDays || {}})
    });
  }

  function mockRetentionPlan(mode) {
    return {
      schema_version: "1.0.0",
      retention_version: "mock",
      mode,
      generated_at: new Date().toISOString(),
      safety: "Mock retention plan",
      total_candidate_records: 0,
      total_candidate_bytes: 0,
      total_deleted_records: 0,
      total_deleted_bytes: 0,
      layers: []
    };
  }

  async function exportLatestFileDrop(limit) {
    if (useMockMode()) {
      return [];
    }
    return request(`${ENDPOINTS.fileDropLatest}?limit=${encodeURIComponent(limit || 20)}`, {
      method: "POST"
    });
  }

  async function health() {
    if (useMockMode()) {
      return {status: "ok", service: "mock"};
    }
    return request(ENDPOINTS.health);
  }

  async function startTestRun() {
    if (useMockMode()) {
      return {
        test_run_id: `mock_test_run_${Date.now()}`,
        record_environment: "test"
      };
    }
    return request(ENDPOINTS.testRuns, {method: "POST"});
  }

  async function testRuns() {
    if (useMockMode()) {
      return [];
    }
    return request(ENDPOINTS.testRuns);
  }

  async function deleteTestRun(testRunId) {
    if (useMockMode()) {
      return {test_run_id: testRunId, deleted: {}};
    }
    return request(ENDPOINTS.testRun(testRunId), {method: "DELETE"});
  }

  async function resetDevelopmentData() {
    if (useMockMode()) {
      return {deleted: {}};
    }
    return request(ENDPOINTS.developmentData, {method: "DELETE"});
  }

  window.NewsApi = {
    analyse,
    recentEvents,
    eventDetail,
    sourceStatus,
    sourceFilings,
    pollSecEdgar,
    pollWorldNews,
    pollDueSources,
    automationStatus,
    automationRunNow,
    favouritesUniverse,
    calibrationReport,
    calibrationOutcomes,
    fileDropStatus,
    marketBars,
    marketRequests,
    storageLayers,
    storageRetentionDryRun,
    applyStorageRetention,
    exportLatestFileDrop,
    health,
    startTestRun,
    testRuns,
    deleteTestRun,
    resetDevelopmentData,
    setSimulateFailure(value) {
      simulateFailure = Boolean(value);
    },
    isSimulatingFailure() {
      return simulateFailure;
    },
    isMockMode: useMockMode,
    endpoints: ENDPOINTS
  };
})();
