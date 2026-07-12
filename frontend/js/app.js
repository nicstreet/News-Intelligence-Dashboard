(function () {
  const state = {
    result: null,
    recentEvents: [],
    selectedEventId: "",
    sources: [],
    sourceFilings: [],
    automation: null,
    universe: null,
    calibration: null,
    fileDrop: null,
    marketBars: [],
    marketRequests: [],
    storage: null,
    storageRetention: {},
    retentionPlan: null,
    currentView: "events",
    selectedStage: 0,
    selectedPanel: "signal",
    selectedJson: "raw_items",
    impactSort: "symbol",
    rawMode: false,
    activeTestRunId: localStorage.getItem("newsIntelligenceActiveTestRunId") || "",
    testRuns: [],
    lastRequest: null,
    lastResponse: null
  };

  const elements = {};

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    bindElements();
    loadFixtureOptions();
    bindEvents();
    updateModeStatus();
    loadFixture(window.NewsFixtures.list[0].id);
    renderAll();
    refreshSources();
    refreshSourceFilings();
    refreshAutomation();
    refreshUniverse();
    refreshCalibration();
    refreshFileDrop();
    refreshMarketData();
    refreshStorage();
    refreshRecent();
    refreshTestRuns();
    checkHealth(false);
  }

  function bindElements() {
    [
      "api-status", "mode-status", "options-menu", "options-sources", "options-storage",
      "options-developer", "options-refresh-dashboard", "fixture-selector", "load-fixture", "news-form",
      "toggle-input-mode", "structured-input", "json-input-wrap", "raw-json", "headline",
      "body", "source-name", "source-type", "source-url", "published-at", "known-ticker",
      "country", "market", "clear-form", "event-summary", "pipeline", "impact-sort",
      "impact-table", "request-id", "panel-signal", "panel-evidence", "panel-cluster",
      "panel-json", "panel-sources", "panel-developer", "json-selector", "json-viewer",
      "copy-json", "download-json", "recent-events", "refresh-recent", "source-status",
      "source-filings", "poll-sec-edgar", "sec-edgar-poll-status", "refresh-source-filings", "error-panel",
      "health-check", "clear-state", "reload-fixtures", "simulate-failure", "raw-request",
      "raw-response", "copy-event-id", "copy-cluster-id", "start-test-run",
      "delete-current-test-run", "reset-development-data", "refresh-test-runs",
      "active-test-run-id", "historical-test-runs", "poll-due-sources",
      "poll-world-news", "sidebar-start-test-run", "automation-status",
      "refresh-automation", "run-automation-now", "automation-run-status",
      "refresh-universe", "universe-summary", "universe-table",
      "refresh-calibration", "calibration-summary", "calibration-report",
      "refresh-file-drop", "export-latest-file-drop", "file-drop-status",
      "file-drop-result", "refresh-event-list", "event-list", "event-detail-meta",
      "event-detail-summary", "event-detail-signal", "event-detail-impacts",
      "event-detail-evidence", "event-detail-cluster", "event-detail-json",
      "refresh-storage", "storage-summary", "storage-visualisation", "storage-layers",
      "dry-run-retention", "apply-retention-policy", "retention-preview",
      "retention-apply-status", "sidebar-events-count", "sidebar-signals-count",
      "sidebar-sources-status", "sidebar-universe-count", "sidebar-calibration-count",
      "sidebar-file-drop-status", "sidebar-market-data-count", "sidebar-active-watch",
      "page-heading", "page-subtitle", "refresh-market-data", "market-bars", "market-requests"
    ].forEach((id) => {
      elements[id] = document.getElementById(id);
    });
  }

  function bindEvents() {
    elements["load-fixture"].addEventListener("click", () => loadFixture(elements["fixture-selector"].value));
    elements["fixture-selector"].addEventListener("change", () => {
      localStorage.setItem("newsIntelligenceLastFixture", elements["fixture-selector"].value);
    });
    elements["toggle-input-mode"].addEventListener("click", toggleInputMode);
    elements["clear-form"].addEventListener("click", clearForm);
    elements["news-form"].addEventListener("submit", submitNews);
    elements["impact-sort"].addEventListener("change", () => {
      state.impactSort = elements["impact-sort"].value;
      renderImpacts();
    });
    elements.pipeline.addEventListener("click", (event) => {
      const button = event.target.closest("[data-stage-index]");
      if (!button) return;
      state.selectedStage = Number(button.dataset.stageIndex);
      state.selectedJson = "stage";
      renderPipeline();
      renderJson();
      activatePanel("json");
    });
    document.querySelectorAll(".tab").forEach((button) => {
      button.addEventListener("click", () => activatePanel(button.dataset.panel));
    });
    document.querySelectorAll("[data-event-detail-tab]").forEach((button) => {
      button.addEventListener("click", () => activateEventDetailTab(button.dataset.eventDetailTab));
    });
    elements["json-selector"].addEventListener("change", () => {
      state.selectedJson = elements["json-selector"].value;
      renderJson();
    });
    elements["copy-json"].addEventListener("click", () => copyText(elements["json-viewer"].textContent || ""));
    elements["download-json"].addEventListener("click", downloadJson);
    elements["options-sources"].addEventListener("click", () => {
      activateView("sources");
      closeOptionsMenu();
    });
    elements["options-storage"].addEventListener("click", () => {
      activateView("storage");
      closeOptionsMenu();
    });
    elements["options-developer"].addEventListener("click", () => {
      activateView("developer");
      closeOptionsMenu();
    });
    elements["options-refresh-dashboard"].addEventListener("click", () => {
      refreshDashboard();
      closeOptionsMenu();
    });
    elements["refresh-recent"].addEventListener("click", refreshRecent);
    elements["refresh-event-list"].addEventListener("click", refreshRecent);
    elements["poll-sec-edgar"].addEventListener("click", pollSecEdgar);
    elements["poll-due-sources"].addEventListener("click", pollDueSources);
    elements["poll-world-news"].addEventListener("click", pollWorldNews);
    elements["sidebar-start-test-run"].addEventListener("click", startNewTestRun);
    elements["refresh-source-filings"].addEventListener("click", refreshSourceFilings);
    elements["refresh-automation"].addEventListener("click", refreshAutomation);
    elements["run-automation-now"].addEventListener("click", runAutomationNow);
    elements["refresh-universe"].addEventListener("click", refreshUniverse);
    elements["refresh-calibration"].addEventListener("click", refreshCalibration);
    elements["refresh-file-drop"].addEventListener("click", refreshFileDrop);
    elements["refresh-market-data"].addEventListener("click", refreshMarketData);
    elements["refresh-storage"].addEventListener("click", refreshStorage);
    elements["dry-run-retention"].addEventListener("click", dryRunRetention);
    elements["apply-retention-policy"].addEventListener("click", applyRetentionPolicy);
    elements["export-latest-file-drop"].addEventListener("click", exportLatestFileDrop);
    elements["recent-events"].addEventListener("click", loadRecentDetail);
    elements["event-list"].addEventListener("click", loadRecentDetail);
    elements["sidebar-active-watch"].addEventListener("click", loadRecentDetail);
    elements["storage-layers"].addEventListener("input", updateStorageRetention);
    elements["health-check"].addEventListener("click", () => checkHealth(true));
    elements["start-test-run"].addEventListener("click", startNewTestRun);
    elements["delete-current-test-run"].addEventListener("click", deleteCurrentTestRun);
    elements["reset-development-data"].addEventListener("click", resetDevelopmentData);
    elements["refresh-test-runs"].addEventListener("click", refreshTestRuns);
    elements["clear-state"].addEventListener("click", clearState);
    elements["reload-fixtures"].addEventListener("click", loadFixtureOptions);
    elements["simulate-failure"].addEventListener("click", toggleFailure);
    elements["copy-event-id"].addEventListener("click", () => copyText(currentEvent()?.event_id || ""));
    elements["copy-cluster-id"].addEventListener("click", () => copyText(currentCluster()?.cluster_id || ""));
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.addEventListener("click", () => activateView(button.dataset.view));
    });
  }

  function loadFixtureOptions() {
    elements["fixture-selector"].innerHTML = window.NewsFixtures.list
      .map((fixture) => `<option value="${NewsRenderers.escapeHtml(fixture.id)}">${NewsRenderers.escapeHtml(fixture.label)}</option>`)
      .join("");
    const last = localStorage.getItem("newsIntelligenceLastFixture");
    if (last && window.NewsFixtures.get(last)) {
      elements["fixture-selector"].value = last;
    }
  }

  function loadFixture(id) {
    const items = window.NewsFixtures.itemsFor(id);
    const first = items[0];
    elements.headline.value = first.headline || "";
    elements.body.value = first.body || "";
    elements["source-name"].value = first.source_name || "";
    elements["source-type"].value = first.source_type || "";
    elements["source-url"].value = first.source_url || "";
    elements["published-at"].value = toLocalInput(first.published_at);
    elements["known-ticker"].value = first.known_ticker || "";
    elements.country.value = first.country || "";
    elements.market.value = first.market || "";
    elements["raw-json"].value = JSON.stringify(items.length === 1 ? first : {items}, null, 2);
    localStorage.setItem("newsIntelligenceLastFixture", id);
  }

  function toggleInputMode() {
    state.rawMode = !state.rawMode;
    elements["structured-input"].classList.toggle("hidden", state.rawMode);
    elements["json-input-wrap"].classList.toggle("hidden", !state.rawMode);
    elements["toggle-input-mode"].textContent = state.rawMode ? "Structured Form" : "Raw JSON";
  }

  function clearForm() {
    elements["news-form"].reset();
    elements["raw-json"].value = "";
  }

  async function submitNews(event) {
    event.preventDefault();
    hideError();
    let payload;
    try {
      payload = state.rawMode ? JSON.parse(elements["raw-json"].value) : formPayload();
      payload = applyTestRun(payload);
    } catch (error) {
      showError({stage: "Input", message: "Invalid JSON", requestId: "not submitted", detail: String(error)});
      return;
    }
    state.lastRequest = payload;
    renderDeveloper();
    setProcessingStages();
    try {
      const result = await window.NewsApi.analyse(payload);
      state.result = result;
      state.lastResponse = result;
      await animateStages(result.stages || []);
      renderAll();
      refreshRecent();
      refreshStorage();
    } catch (error) {
      showError(error);
      setFailedStage(error.stage || "API", error.message);
    }
  }

  function formPayload() {
    const published = elements["published-at"].value
      ? new Date(elements["published-at"].value).toISOString()
      : new Date().toISOString();
    const payload = {
      headline: elements.headline.value,
      body: elements.body.value,
      source_name: elements["source-name"].value,
      source_type: elements["source-type"].value,
      source_url: elements["source-url"].value || null,
      published_at: published,
      known_ticker: elements["known-ticker"].value || null,
      country: elements.country.value || null,
      market: elements.market.value || null
    };
    if (!payload.headline) {
      throw new Error("Headline is required.");
    }
    return payload;
  }

  function setProcessingStages() {
    state.result = {
      request_id: "processing",
      stages: ["Raw News", "Normalised News", "Event Classification", "Entity Resolution", "Event Cluster", "Instrument Impacts", "News Signal"]
        .map((name) => ({name, status: "PROCESSING"})),
      raw_items: [],
      normalised_items: [],
      events: [],
      clusters: [],
      impacts: [],
      signals: [],
      errors: []
    };
    renderAll();
  }

  async function animateStages(stages) {
    const animated = stages.map((stage) => ({...stage, status: "NOT_STARTED"}));
    state.result.stages = animated;
    for (let index = 0; index < animated.length; index += 1) {
      animated[index].status = "PROCESSING";
      renderPipeline();
      await sleep(70);
      animated[index].status = stages[index].status || "COMPLETED";
      renderPipeline();
    }
    state.result.stages = stages;
  }

  function setFailedStage(stageName, summary) {
    const stages = state.result ? state.result.stages || [] : [];
    const index = Math.max(0, stages.findIndex((stage) => stage.name === stageName));
    if (stages[index]) {
      stages[index].status = "FAILED";
      stages[index].error = {stage: stageName, summary, request_id: "unavailable"};
    }
    renderPipeline();
  }

  function renderAll() {
    renderEventSummary();
    renderPipeline();
    renderImpacts();
    renderSignal();
    renderEvidence();
    renderCluster();
    renderJsonOptions();
    renderJson();
    renderEventWorkspace();
    renderSources();
    renderAutomation();
    renderUniverse();
    renderCalibration();
    renderFileDrop();
    renderMarketData();
    renderStorage();
    renderDeveloper();
    renderSidebar();
    renderView();
  }

  function renderEventSummary() {
    const event = currentEvent();
    elements["event-summary"].innerHTML = window.NewsRenderers.renderEventSummary(event);
    elements["request-id"].textContent = state.result ? `Request: ${state.result.request_id}` : "No request";
  }

  function renderPipeline() {
    elements.pipeline.innerHTML = window.NewsRenderers.renderPipeline(
      state.result ? state.result.stages : null,
      state.selectedStage
    );
  }

  function renderImpacts() {
    elements["impact-table"].innerHTML = window.NewsRenderers.renderImpacts(
      state.result ? state.result.impacts : [],
      state.impactSort
    );
  }

  function renderSignal() {
    elements["panel-signal"].innerHTML = window.NewsRenderers.renderSignal(currentSignal());
  }

  function renderEvidence() {
    elements["panel-evidence"].innerHTML = window.NewsRenderers.renderEvidence(
      currentEvent(),
      currentCluster(),
      currentSignal()
    );
  }

  function renderCluster() {
    elements["panel-cluster"].innerHTML = window.NewsRenderers.renderCluster(currentCluster());
  }

  function renderSources() {
    elements["source-status"].innerHTML = window.NewsRenderers.renderSources(state.sources);
    elements["source-filings"].innerHTML = window.NewsRenderers.renderSourceFilings(state.sourceFilings);
  }

  function renderEventWorkspace() {
    elements["event-list"].innerHTML = window.NewsRenderers.renderEventRows(
      state.recentEvents,
      state.selectedEventId
    );
    const event = currentEvent();
    const cluster = currentCluster();
    const signal = currentSignal();
    elements["event-detail-meta"].textContent = event
      ? `${event.event_type || "event"} / ${event.primary_symbol || "market"}`
      : "Select an event";
    elements["event-detail-summary"].innerHTML = window.NewsRenderers.renderEventSummary(event);
    elements["event-detail-signal"].innerHTML = window.NewsRenderers.renderSignal(signal);
    elements["event-detail-impacts"].innerHTML = renderImpactTable(
      state.result ? state.result.impacts : []
    );
    elements["event-detail-evidence"].innerHTML = window.NewsRenderers.renderEvidence(
      event,
      cluster,
      signal
    );
    elements["event-detail-cluster"].innerHTML = window.NewsRenderers.renderCluster(cluster);
    elements["event-detail-json"].textContent = JSON.stringify(
      {
        event,
        cluster,
        impacts: state.result ? state.result.impacts : [],
        signals: state.result ? state.result.signals : []
      },
      null,
      2
    );
    renderSidebar();
  }

  function renderAutomation() {
    elements["automation-status"].innerHTML = window.NewsRenderers.renderAutomation(state.automation);
  }

  function renderUniverse() {
    elements["universe-summary"].innerHTML = window.NewsRenderers.renderUniverseSummary(state.universe);
    elements["universe-table"].innerHTML = window.NewsRenderers.renderUniverseTable(state.universe);
  }

  function renderCalibration() {
    elements["calibration-summary"].innerHTML = window.NewsRenderers.renderCalibrationSummary(state.calibration);
    elements["calibration-report"].innerHTML = window.NewsRenderers.renderCalibrationReport(state.calibration);
  }

  function renderFileDrop() {
    elements["file-drop-status"].innerHTML = window.NewsRenderers.renderFileDropStatus(state.fileDrop);
  }

  function renderMarketData() {
    elements["market-bars"].innerHTML = window.NewsRenderers.renderMarketBars(state.marketBars);
    elements["market-requests"].innerHTML = window.NewsRenderers.renderMarketRequests(state.marketRequests);
  }

  function renderStorage() {
    elements["storage-summary"].innerHTML = window.NewsRenderers.renderStorageSummary(
      state.storage,
      state.storageRetention
    );
    elements["storage-visualisation"].innerHTML = window.NewsRenderers.renderStorageVisualisation(
      state.storage,
      state.storageRetention
    );
    elements["storage-layers"].innerHTML = window.NewsRenderers.renderStorageLayers(
      state.storage,
      state.storageRetention
    );
    elements["retention-preview"].innerHTML = window.NewsRenderers.renderRetentionPlan(
      state.retentionPlan
    );
  }

  function renderJsonOptions() {
    const options = [
      ["raw_items", "Raw input"],
      ["normalised_items", "Normalised item"],
      ["events", "Classified event"],
      ["entities", "Resolved entities"],
      ["clusters", "Event cluster"],
      ["event_versions", "Event versions"],
      ["impacts", "Instrument impacts"],
      ["signals", "Final news signal"],
      ["signal_snapshots", "Signal snapshots"],
      ["stage", "Selected pipeline stage"]
    ];
    elements["json-selector"].innerHTML = options
      .map(([value, label]) => `<option value="${value}">${label}</option>`)
      .join("");
    elements["json-selector"].value = state.selectedJson;
  }

  function renderJson() {
    const result = state.result || {};
    let payload = result[state.selectedJson];
    if (state.selectedJson === "entities") {
      payload = (result.events || []).map((event) => event.entities || []);
    }
    if (state.selectedJson === "event_versions") {
      payload = (result.clusters || []).map((cluster) => cluster.event_versions || []);
    }
    if (state.selectedJson === "signal_snapshots") {
      payload = (result.clusters || []).map((cluster) => cluster.signal_snapshots || []);
    }
    if (state.selectedJson === "stage") {
      payload = result.stages ? result.stages[state.selectedStage] : null;
    }
    elements["json-viewer"].textContent = JSON.stringify(payload || null, null, 2);
  }

  function renderDeveloper() {
    elements["active-test-run-id"].textContent = state.activeTestRunId || "none";
    elements["historical-test-runs"].innerHTML = window.NewsRenderers.renderTestRuns(state.testRuns);
    elements["raw-request"].textContent = JSON.stringify(state.lastRequest || null, null, 2);
    elements["raw-response"].textContent = JSON.stringify(state.lastResponse || null, null, 2);
  }

  function applyTestRun(payload) {
    if (!state.activeTestRunId) {
      return payload;
    }
    const decorated = JSON.parse(JSON.stringify(payload));
    decorated.test_run_id = state.activeTestRunId;
    decorated.record_environment = "test";
    if (Array.isArray(decorated)) {
      return {
        test_run_id: state.activeTestRunId,
        record_environment: "test",
        items: decorated
      };
    }
    if (Array.isArray(decorated.items)) {
      return decorated;
    }
    return decorated;
  }

  async function refreshSources() {
    try {
      state.sources = await window.NewsApi.sourceStatus();
      renderSources();
      renderSidebar();
    } catch (error) {
      state.sources = [];
      showError(error);
      renderSidebar();
    }
  }

  async function refreshSourceFilings() {
    try {
      state.sourceFilings = await window.NewsApi.sourceFilings();
      renderSources();
    } catch (error) {
      state.sourceFilings = [];
      if (!window.NewsApi.isMockMode()) {
        showError(error);
      }
      renderSources();
    }
  }

  async function refreshAutomation() {
    try {
      state.automation = await window.NewsApi.automationStatus();
      renderAutomation();
    } catch (error) {
      state.automation = null;
      if (!window.NewsApi.isMockMode()) {
        showError(error);
      }
      renderAutomation();
    }
  }

  async function runAutomationNow() {
    hideError();
    setAutomationStatus("Automation: running...", "processing");
    elements["run-automation-now"].disabled = true;
    try {
      const result = await window.NewsApi.automationRunNow(false);
      state.lastResponse = result;
      await refreshSources();
      await refreshSourceFilings();
      await refreshAutomation();
      await refreshRecent();
      await refreshStorage();
      renderDeveloper();
      setAutomationStatus(`Automation: ${result.ingested_count || 0} ingested`, "");
    } catch (error) {
      setAutomationStatus("Automation: failed", "error");
      showError(error);
    } finally {
      elements["run-automation-now"].disabled = false;
    }
  }

  async function refreshUniverse() {
    try {
      state.universe = await window.NewsApi.favouritesUniverse();
      renderUniverse();
      renderSidebar();
    } catch (error) {
      state.universe = null;
      if (!window.NewsApi.isMockMode()) {
        showError(error);
      }
      renderUniverse();
      renderSidebar();
    }
  }

  async function refreshCalibration() {
    try {
      state.calibration = await window.NewsApi.calibrationReport();
      renderCalibration();
      renderSidebar();
    } catch (error) {
      state.calibration = null;
      if (!window.NewsApi.isMockMode()) {
        showError(error);
      }
      renderCalibration();
      renderSidebar();
    }
  }

  async function refreshFileDrop() {
    try {
      state.fileDrop = await window.NewsApi.fileDropStatus();
      renderFileDrop();
      renderSidebar();
    } catch (error) {
      state.fileDrop = null;
      if (!window.NewsApi.isMockMode()) {
        showError(error);
      }
      renderFileDrop();
      renderSidebar();
    }
  }

  async function refreshMarketData() {
    try {
      const [bars, requests] = await Promise.all([
        window.NewsApi.marketBars(),
        window.NewsApi.marketRequests()
      ]);
      state.marketBars = bars || [];
      state.marketRequests = requests || [];
      renderMarketData();
      renderSidebar();
    } catch (error) {
      state.marketBars = [];
      state.marketRequests = [];
      if (!window.NewsApi.isMockMode()) {
        showError(error);
      }
      renderMarketData();
      renderSidebar();
    }
  }

  async function refreshStorage() {
    try {
      state.storage = await window.NewsApi.storageLayers();
      initialiseStorageRetention();
      renderStorage();
    } catch (error) {
      state.storage = null;
      if (!window.NewsApi.isMockMode()) {
        showError(error);
      }
      renderStorage();
    }
  }

  async function dryRunRetention() {
    hideError();
    setRetentionStatus("Retention: dry run...", "processing");
    elements["dry-run-retention"].disabled = true;
    try {
      state.retentionPlan = await window.NewsApi.storageRetentionDryRun(state.storageRetention);
      state.lastResponse = state.retentionPlan;
      renderStorage();
      renderDeveloper();
      setRetentionStatus("Retention: dry run ready", "");
    } catch (error) {
      setRetentionStatus("Retention: dry run failed", "error");
      showError(error);
    } finally {
      elements["dry-run-retention"].disabled = false;
    }
  }

  async function applyRetentionPolicy() {
    const confirmed = window.confirm("Apply retention policy? This deletes eligible development/test records and configured file-drop JSON only. Production-labelled records are retained.");
    if (!confirmed) return;
    hideError();
    setRetentionStatus("Retention: applying...", "processing");
    elements["apply-retention-policy"].disabled = true;
    try {
      state.retentionPlan = await window.NewsApi.applyStorageRetention(state.storageRetention);
      state.lastResponse = state.retentionPlan;
      await refreshStorage();
      await refreshRecent();
      await refreshSourceFilings();
      renderAll();
      setRetentionStatus(`Retention: ${state.retentionPlan.total_deleted_records || 0} deleted`, "");
    } catch (error) {
      setRetentionStatus("Retention: apply failed", "error");
      showError(error);
    } finally {
      elements["apply-retention-policy"].disabled = false;
    }
  }

  async function pollSecEdgar() {
    hideError();
    setSecPollStatus("SEC: polling...", "processing");
    elements["poll-sec-edgar"].disabled = true;
    try {
      const result = await window.NewsApi.pollSecEdgar(true);
      state.lastResponse = result;
      await refreshSources();
      await refreshSourceFilings();
      await refreshAutomation();
      await refreshRecent();
      await refreshStorage();
      setSecPollStatus(`SEC: ${result.ingested_count || 0} new, ${result.skipped_count || 0} skipped`, "");
      renderDeveloper();
    } catch (error) {
      setSecPollStatus("SEC: failed", "error");
      showError(error);
    } finally {
      elements["poll-sec-edgar"].disabled = false;
    }
  }

  async function pollWorldNews() {
    hideError();
    try {
      const result = await window.NewsApi.pollWorldNews(true);
      state.lastResponse = result;
      await refreshSources();
      await refreshSourceFilings();
      await refreshAutomation();
      await refreshRecent();
      await refreshStorage();
      renderDeveloper();
      activateView("sources");
    } catch (error) {
      showError(error);
    }
  }

  async function pollDueSources() {
    hideError();
    try {
      const result = await window.NewsApi.pollDueSources(false);
      state.lastResponse = result;
      await refreshSources();
      await refreshSourceFilings();
      await refreshAutomation();
      await refreshRecent();
      await refreshStorage();
      renderDeveloper();
      activateView("sources");
    } catch (error) {
      showError(error);
    }
  }

  async function exportLatestFileDrop() {
    hideError();
    try {
      const result = await window.NewsApi.exportLatestFileDrop(20);
      state.lastResponse = result;
      elements["file-drop-result"].textContent = JSON.stringify(result, null, 2);
      await refreshFileDrop();
      await refreshStorage();
      renderDeveloper();
    } catch (error) {
      showError(error);
    }
  }

  function setSecPollStatus(message, stateClass) {
    const status = elements["sec-edgar-poll-status"];
    status.textContent = message;
    status.classList.toggle("muted", !stateClass);
    status.classList.toggle("processing", stateClass === "processing");
    status.classList.toggle("error", stateClass === "error");
  }

  function setAutomationStatus(message, stateClass) {
    const status = elements["automation-run-status"];
    status.textContent = message;
    status.classList.toggle("muted", !stateClass);
    status.classList.toggle("processing", stateClass === "processing");
    status.classList.toggle("error", stateClass === "error");
  }

  async function refreshRecent() {
    try {
      const events = await window.NewsApi.recentEvents();
      state.recentEvents = events || [];
      elements["recent-events"].innerHTML = window.NewsRenderers.renderRecent(
        state.recentEvents,
        state.selectedEventId
      );
      renderEventWorkspace();
      renderSidebar();
    } catch (error) {
      state.recentEvents = [];
      elements["recent-events"].innerHTML = window.NewsRenderers.renderRecent([]);
      renderEventWorkspace();
      renderSidebar();
      if (!window.NewsApi.isMockMode()) {
        showError(error);
      }
    }
  }

  async function refreshTestRuns() {
    try {
      state.testRuns = await window.NewsApi.testRuns();
      renderDeveloper();
    } catch (error) {
      state.testRuns = [];
      if (!window.NewsApi.isMockMode()) {
        showError(error);
      }
      renderDeveloper();
    }
  }

  async function loadRecentDetail(event) {
    if (event.target.closest("a")) return;
    const row = event.target.closest("[data-event-id]");
    if (!row) return;
    try {
      const detail = await window.NewsApi.eventDetail(row.dataset.eventId);
      state.selectedEventId = row.dataset.eventId;
      state.result = {
        request_id: `reloaded_${row.dataset.eventId}`,
        stages: [],
        raw_items: [],
        normalised_items: [],
        events: detail.event ? [detail.event] : [],
        clusters: detail.cluster ? [detail.cluster] : [],
        impacts: detail.impacts || [],
        signals: detail.signals || [],
        errors: []
      };
      state.lastResponse = detail;
      renderAll();
    } catch (error) {
      showError(error);
    }
  }

  async function checkHealth(showPanel) {
    try {
      const health = await window.NewsApi.health();
      elements["api-status"].textContent = `Backend: ${String(health.status || "ok").toUpperCase()}`;
      elements["api-status"].classList.remove("muted");
      if (showPanel) {
        state.lastResponse = health;
        renderDeveloper();
      }
    } catch (error) {
      elements["api-status"].textContent = "Backend: OFFLINE";
      elements["api-status"].classList.add("muted");
      if (showPanel) showError(error);
    }
  }

  function clearState() {
    state.result = null;
    state.lastRequest = null;
    state.lastResponse = null;
    localStorage.removeItem("newsIntelligenceLastFixture");
    renderAll();
    hideError();
  }

  async function startNewTestRun() {
    hideError();
    try {
      const run = await window.NewsApi.startTestRun();
      state.activeTestRunId = run.test_run_id;
      localStorage.setItem("newsIntelligenceActiveTestRunId", state.activeTestRunId);
      state.result = null;
      state.lastRequest = null;
      state.lastResponse = run;
      await refreshTestRuns();
      renderAll();
    } catch (error) {
      showError(error);
    }
  }

  async function deleteCurrentTestRun() {
    if (!state.activeTestRunId) {
      showError({stage: "Test Run", message: "No active test run is selected.", requestId: "not submitted"});
      return;
    }
    const confirmed = window.confirm(`Delete records for test run ${state.activeTestRunId}?`);
    if (!confirmed) return;
    hideError();
    try {
      const result = await window.NewsApi.deleteTestRun(state.activeTestRunId);
      state.activeTestRunId = "";
      localStorage.removeItem("newsIntelligenceActiveTestRunId");
      state.result = null;
      state.lastRequest = null;
      state.lastResponse = result;
      await refreshRecent();
      await refreshTestRuns();
      await refreshStorage();
      renderAll();
    } catch (error) {
      showError(error);
    }
  }

  async function resetDevelopmentData() {
    const confirmed = window.confirm("Delete development and test records? Production-labelled records will be retained.");
    if (!confirmed) return;
    hideError();
    try {
      const result = await window.NewsApi.resetDevelopmentData();
      state.activeTestRunId = "";
      localStorage.removeItem("newsIntelligenceActiveTestRunId");
      state.result = null;
      state.lastRequest = null;
      state.lastResponse = result;
      await refreshRecent();
      await refreshTestRuns();
      await refreshStorage();
      renderAll();
    } catch (error) {
      showError(error);
    }
  }

  function toggleFailure() {
    const next = !window.NewsApi.isSimulatingFailure();
    window.NewsApi.setSimulateFailure(next);
    elements["simulate-failure"].textContent = next ? "Stop Simulated Failure" : "Simulate Backend Failure";
  }

  function activateView(name) {
    if (!name) return;
    state.currentView = name;
    if (name === "sources") activatePanel("sources");
    if (name === "json") activatePanel("json");
    if (name === "developer") activatePanel("developer");
    if (name === "signals") activatePanel("signal");
    if (name === "events") activatePanel("cluster");
    renderView();
  }

  function renderView() {
    renderPageTitle();
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === state.currentView);
    });
    document.querySelectorAll(".view-section").forEach((section) => {
      const views = String(section.dataset.views || "").split(/\s+/);
      section.classList.toggle("view-hidden", !views.includes(state.currentView));
    });
  }

  function renderPageTitle() {
    const titles = {
      events: ["Events", "Live event intelligence, signal state, source evidence and calibration readiness."],
      overview: ["Overview", "Pipeline status, recent events, source automation and fixture controls."],
      signals: ["Signals", "Instrument-level signal snapshots, confidence, quality and impact reasoning."],
      sources: ["Sources", "Connector status, polling controls and source lineage records."],
      universe: ["Favourites", "Configured watch universe, themes, exchanges and benchmarks."],
      calibration: ["Calibration", "Historical outcome scaffolding and profile readiness."],
      "market-data": ["Market Data", "Cached EODHD bars and request audit records for calibration."],
      "file-drop": ["File Drop", "Atomic JSON exports for downstream trading-app ingestion."],
      json: ["JSON / Audit", "Raw event, cluster, signal and pipeline contract inspection."],
      developer: ["Developer", "Fixture test runs, reset controls and request/response inspection."],
      storage: ["Storage / Retention", "Layer storage, retention sliders and cleanup previews."]
    };
    const [heading, subtitle] = titles[state.currentView] || titles.events;
    if (elements["page-heading"]) elements["page-heading"].textContent = heading;
    if (elements["page-subtitle"]) elements["page-subtitle"].textContent = subtitle;
  }

  function activatePanel(name) {
    state.selectedPanel = name;
    document.querySelectorAll(".tab").forEach((button) => {
      button.classList.toggle("active", button.dataset.panel === name);
    });
    ["signal", "evidence", "cluster", "json", "sources", "developer"].forEach((panel) => {
      elements[`panel-${panel}`].classList.toggle("hidden", panel !== name);
    });
  }

  function activateEventDetailTab(name) {
    if (!name) return;
    document.querySelectorAll("[data-event-detail-tab]").forEach((button) => {
      button.classList.toggle("active", button.dataset.eventDetailTab === name);
    });
    document.querySelectorAll("[data-event-detail-panel]").forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.eventDetailPanel !== name);
    });
  }

  function renderSidebar() {
    setText("sidebar-events-count", String((state.recentEvents || []).length));
    setText("sidebar-signals-count", String(state.result && state.result.signals ? state.result.signals.length : 0));
    setText("sidebar-sources-status", sourceStatusLabel());
    setText("sidebar-universe-count", String(state.universe && state.universe.instruments ? state.universe.instruments.length : 0));
    setText("sidebar-calibration-count", String(state.calibration && state.calibration.signal_count ? state.calibration.signal_count : 0));
    setText("sidebar-file-drop-status", state.fileDrop && state.fileDrop.enabled ? "On" : "Idle");
    setText("sidebar-market-data-count", String((state.marketBars || []).length));
    if (elements["sidebar-active-watch"]) {
      elements["sidebar-active-watch"].innerHTML = window.NewsRenderers.renderSidebarWatch(
        state.recentEvents || []
      );
    }
  }

  function sourceStatusLabel() {
    const sources = state.sources || [];
    if (sources.length === 0) return "n/a";
    if (sources.some((source) => String(source.current_status || "").toUpperCase() === "ERROR")) return "ERR";
    if (sources.some((source) => source.stale)) return "STALE";
    return "OK";
  }

  function setText(id, value) {
    if (elements[id]) elements[id].textContent = value;
  }

  function showError(error) {
    elements["error-panel"].innerHTML = window.NewsRenderers.renderError(error);
    elements["error-panel"].classList.remove("hidden");
  }

  function hideError() {
    elements["error-panel"].classList.add("hidden");
    elements["error-panel"].innerHTML = "";
  }

  function updateModeStatus() {
    elements["mode-status"].textContent = window.NewsApi.isMockMode()
      ? "Runtime: MOCK DATA"
      : "Runtime: LIVE BACKEND";
  }

  function initialiseStorageRetention() {
    const layers = state.storage && state.storage.layers ? state.storage.layers : [];
    layers.forEach((layer) => {
      if (!layer.adjustable || state.storageRetention[layer.layer_key]) return;
      state.storageRetention[layer.layer_key] = Number(layer.retention_days || 365);
    });
  }

  function updateStorageRetention(event) {
    const input = event.target.closest("[data-retention-layer]");
    if (!input) return;
    state.storageRetention[input.dataset.retentionLayer] = Number(input.value);
    renderStorage();
  }

  function setRetentionStatus(message, stateClass) {
    const status = elements["retention-apply-status"];
    status.textContent = message;
    status.classList.toggle("muted", !stateClass);
    status.classList.toggle("processing", stateClass === "processing");
    status.classList.toggle("error", stateClass === "error");
  }

  function currentEvent() {
    if (!state.result || !state.result.events || state.result.events.length === 0) return null;
    return state.result.events.find((event) => event.event_status === "denied")
      || state.result.events.find((event) => event.event_type === "merger_acquisition")
      || state.result.events[state.result.events.length - 1];
  }

  function currentCluster() {
    if (!state.result || !state.result.clusters || state.result.clusters.length === 0) return null;
    const event = currentEvent();
    return state.result.clusters.find((cluster) => event && cluster.cluster_id === event.cluster_id)
      || state.result.clusters[0];
  }

  function currentSignal() {
    if (!state.result || !state.result.signals || state.result.signals.length === 0) return null;
    const event = currentEvent();
    return state.result.signals.find((signal) => event && signal.event_id === event.event_id)
      || state.result.signals[0];
  }

  function toLocalInput(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const offset = date.getTimezoneOffset();
    const local = new Date(date.getTime() - offset * 60000);
    return local.toISOString().slice(0, 16);
  }

  function sleep(ms) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }

  async function copyText(value) {
    if (!value) return;
    await navigator.clipboard.writeText(value);
  }

  function downloadJson() {
    const blob = new Blob([elements["json-viewer"].textContent || "null"], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${state.selectedJson || "asterius-news-intelligence"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function refreshDashboard() {
    await Promise.all([
      refreshSources(),
      refreshSourceFilings(),
      refreshAutomation(),
      refreshUniverse(),
      refreshCalibration(),
      refreshFileDrop(),
      refreshMarketData(),
      refreshStorage(),
      refreshRecent(),
      refreshTestRuns(),
      checkHealth(false)
    ]);
  }

  function closeOptionsMenu() {
    if (elements["options-menu"]) {
      elements["options-menu"].open = false;
    }
  }

  function renderImpactTable(impacts) {
    return `<div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Type</th>
            <th>Relationship</th>
            <th>Direction</th>
            <th>Strength</th>
            <th>Relevance</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>${window.NewsRenderers.renderCompactImpacts(impacts || [])}</tbody>
      </table>
    </div>`;
  }
})();
