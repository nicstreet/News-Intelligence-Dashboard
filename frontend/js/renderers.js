(function () {
  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function number(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "n/a";
    }
    return Number(value).toFixed(digits);
  }

  function upper(value) {
    return String(value || "n/a").replaceAll("_", " ").toUpperCase();
  }

  function metric(label, value, extraClass) {
    return `<div class="metric ${extraClass || ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
  }

  function renderEventSummary(event) {
    if (!event) {
      return metric("Status", "No event analysed");
    }
    const analysis = event.analysis || {};
    const roles = (event.strategy_roles || []).join(", ");
    return [
      metric("Event ID", event.event_id),
      metric("Cluster ID", event.cluster_id || "pending"),
      metric("Event type", upper(event.event_type)),
      metric("Subtype", upper(event.event_subtype)),
      metric("Status", upper(event.event_status)),
      metric("Direction", upper(analysis.direction), `direction-${upper(analysis.direction)}`),
      metric("Strength", number(analysis.directional_strength, 2)),
      metric("Confidence", number(analysis.confidence, 2)),
      metric("Quality", number(analysis.quality, 2)),
      metric("Surprise", number(analysis.surprise, 2)),
      metric("Novelty", number(analysis.novelty, 2)),
      metric("Persistence", upper(analysis.expected_persistence)),
      metric("Strategy roles", roles || "none"),
      metric("Headline", event.headline)
    ].join("");
  }

  function renderPipeline(stages, selectedIndex) {
    const names = ["Raw News", "Normalised News", "Event Classification", "Entity Resolution", "Event Cluster", "Instrument Impacts", "News Signal"];
    const stageList = stages && stages.length ? stages : names.map((name) => ({name, status: "NOT_STARTED"}));
    return stageList.map((stage, index) => {
      const active = index === selectedIndex ? " active" : "";
      const status = stage.status || "NOT_STARTED";
      return `<button class="stage${active}" data-stage-index="${index}" type="button">
        <span class="name">${escapeHtml(stage.name)}</span>
        <span class="state state-${escapeHtml(status)}">${escapeHtml(status)}</span>
      </button>`;
    }).join("");
  }

  function renderImpacts(impacts, sortKey) {
    if (!impacts || impacts.length === 0) {
      return `<tr><td colspan="9">No instrument impacts available.</td></tr>`;
    }
    const sorted = [...impacts].sort((left, right) => compareImpact(left, right, sortKey));
    return sorted.map((impact) => `<tr>
      <td>${escapeHtml(impact.symbol)}</td>
      <td>${escapeHtml(impact.entity_type)}</td>
      <td>${escapeHtml(impact.relationship)}</td>
      <td>${escapeHtml(impact.scope)}</td>
      <td class="direction-${upper(impact.direction)}">${upper(impact.direction)}</td>
      <td>${number(impact.directional_strength, 2)}</td>
      <td>${number(impact.relevance, 2)}</td>
      <td>${number(impact.confidence, 2)}</td>
      <td>${escapeHtml(impact.reason)}</td>
    </tr>`).join("");
  }

  function compareImpact(left, right, sortKey) {
    if (sortKey === "symbol") {
      return String(left.symbol).localeCompare(String(right.symbol));
    }
    return Number(right[sortKey] || 0) - Number(left[sortKey] || 0);
  }

  function renderSignal(signal) {
    if (!signal) {
      return `<div class="metric"><span>Status</span><strong>No signal generated.</strong></div>`;
    }
    const metrics = signal.signal || {};
    const decision = signal.decision || {};
    return `<div class="signal-grid">
      ${metric("Instrument", signal.instrument ? signal.instrument.symbol : "n/a")}
      ${metric("Direction", upper(metrics.direction), `direction-${upper(metrics.direction)}`)}
      ${metric("Strength", number(metrics.directional_strength, 2))}
      ${metric("Confidence", number(metrics.confidence, 2))}
      ${metric("Quality", number(metrics.quality, 2))}
      ${metric("Freshness", number(metrics.freshness, 2))}
      ${metric("Time horizon", upper(metrics.time_horizon))}
      ${metric("Strategy roles", (signal.roles || []).join(", "))}
      ${metric("Can trigger trade", String(Boolean(decision.can_trigger_trade)).toUpperCase())}
      ${metric("Can confirm trade", String(Boolean(decision.can_confirm_trade)).toUpperCase())}
      ${metric("Can veto trade", String(Boolean(decision.can_veto_trade)).toUpperCase())}
      ${metric("Requires technical confirmation", String(Boolean(decision.requires_technical_confirmation)).toUpperCase())}
      ${metric("Expiry time", signal.expiry_time || "n/a")}
    </div>`;
  }

  function renderEvidence(event, cluster, signal) {
    if (!event) {
      return `<div class="metric"><span>Status</span><strong>No evidence available.</strong></div>`;
    }
    const source = event.source || {};
    const evidence = signal ? signal.evidence || {} : {};
    const sourceUrl = source.source_url
      ? `<a href="${escapeHtml(source.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.source_url)}</a>`
      : "not supplied";
    return `<div class="evidence-grid">
      ${metric("Source name", source.source_name)}
      ${metric("Source class", source.source_type)}
      ${metric("Source credibility", number(source.source_credibility, 2))}
      ${metric("Primary source present", String(Boolean(evidence.primary_source_present)).toUpperCase())}
      ${metric("Independent source count", evidence.independent_source_count || (cluster ? cluster.independent_source_count : "n/a"))}
      ${metric("Article count", evidence.article_count || (cluster ? cluster.article_count : "n/a"))}
      ${metric("Duplicate count", evidence.duplicate_count || (cluster ? cluster.duplicate_count : "n/a"))}
      ${metric("Update count", cluster ? cluster.update_count : "n/a")}
      ${metric("First publication", cluster ? cluster.first_publication_at : event.timestamps.published_at)}
      ${metric("Latest update", cluster ? cluster.latest_material_update_at : event.timestamps.processed_at)}
      ${metric("Confirmation status", upper(event.event_status))}
      ${metric("Contradictions detected", String(Boolean(event.contradictions_detected || (cluster && cluster.contradictions_detected))).toUpperCase())}
      <div class="metric"><span>Source URL</span><strong>${sourceUrl}</strong></div>
    </div>`;
  }

  function renderCluster(cluster) {
    if (!cluster) {
      return `<p>No cluster available.</p>`;
    }
    const articles = cluster.articles || cluster.items || [];
    const rows = articles.map((item) => `<tr>
      <td>${escapeHtml(item.headline)}</td>
      <td>${escapeHtml(item.source_name)}</td>
      <td>${escapeHtml(item.published_at)}</td>
      <td>${upper(item.classification || (item.material_update ? "MATERIAL_UPDATE" : item.duplicate ? "DUPLICATE" : "NEW_EVENT"))}</td>
      <td>${String(Boolean(item.duplicate)).toUpperCase()}</td>
      <td>${String(Boolean(item.material_update)).toUpperCase()}</td>
      <td>${upper(item.confirmation_status)}</td>
      <td>${escapeHtml(item.content_hash)}</td>
      <td>${escapeHtml(item.canonical_event_id)}</td>
    </tr>`).join("");
    return `<div class="metric-grid">
      ${metric("Cluster ID", cluster.cluster_id)}
      ${metric("Article count", cluster.article_count)}
      ${metric("Duplicate count", cluster.duplicate_count)}
      ${metric("Update count", cluster.update_count || 0)}
      ${metric("Independent sources", cluster.independent_source_count)}
      ${metric("Latest article", cluster.latest_article_at || "n/a")}
      ${metric("Signal snapshots", cluster.signal_snapshots ? cluster.signal_snapshots.length : 0)}
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Headline</th>
            <th>Source</th>
            <th>Published</th>
            <th>Classification</th>
            <th>Duplicate</th>
            <th>Material update</th>
            <th>Status</th>
            <th>Content hash</th>
            <th>Canonical event</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  function renderSources(sources) {
    if (!sources || sources.length === 0) {
      return `<p>No source connector status available.</p>`;
    }
    const rows = sources.map((source) => `<tr>
      <td>${escapeHtml(source.source_name)}</td>
      <td>${escapeHtml(source.country_or_region)}</td>
      <td>${escapeHtml(source.source_class)}</td>
      <td>${escapeHtml(source.connector_type)}</td>
      <td>${String(Boolean(source.enabled)).toUpperCase()}</td>
      <td>${escapeHtml(source.last_successful_ingestion || "n/a")}</td>
      <td>${escapeHtml(source.last_failure || "n/a")}</td>
      <td>${escapeHtml(source.items_ingested)}</td>
      <td>${escapeHtml(source.current_status)}</td>
    </tr>`).join("");
    return `<div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Source name</th>
            <th>Region</th>
            <th>Class</th>
            <th>Connector</th>
            <th>Enabled</th>
            <th>Last success</th>
            <th>Last failure</th>
            <th>Items</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  function renderSourceFilings(filings) {
    if (!filings || filings.length === 0) {
      return `<tr><td colspan="7">No ingested filings available.</td></tr>`;
    }
    return filings.map((filing) => `<tr>
      <td>${escapeHtml(filing.filing_time || "n/a")}</td>
      <td>${escapeHtml(filing.ticker || "n/a")}</td>
      <td>${escapeHtml(filing.form_type || "n/a")}</td>
      <td>${escapeHtml(filing.company || "n/a")}</td>
      <td><a href="${escapeHtml(filing.filing_url || "#")}" target="_blank" rel="noopener noreferrer">${escapeHtml(filing.accession_number || "n/a")}</a></td>
      <td>${escapeHtml((filing.filing_sections || []).join(", ") || "n/a")}</td>
      <td>${escapeHtml(filing.event_id || "pending")}</td>
    </tr>`).join("");
  }

  function renderRecent(events) {
    if (!events || events.length === 0) {
      return `<tr><td colspan="8">No recent events available.</td></tr>`;
    }
    return events.map((event) => `<tr data-event-id="${escapeHtml(event.event_id)}">
      <td>${escapeHtml(event.timestamps ? event.timestamps.processed_at : "n/a")}</td>
      <td>${upper(event.event_type)}</td>
      <td>${escapeHtml(event.primary_symbol || "n/a")}</td>
      <td>${escapeHtml(event.headline)}</td>
      <td class="direction-${upper(event.analysis ? event.analysis.direction : "neutral")}">${upper(event.analysis ? event.analysis.direction : "neutral")}</td>
      <td>${number(event.analysis ? event.analysis.confidence : null, 2)}</td>
      <td>${escapeHtml(event.source ? event.source.source_name : "n/a")}</td>
      <td>${escapeHtml(event.cluster_id || "n/a")}</td>
    </tr>`).join("");
  }

  function renderTestRuns(testRuns) {
    if (!testRuns || testRuns.length === 0) {
      return `<tr><td colspan="5">No historical test runs available.</td></tr>`;
    }
    return testRuns.map((run) => `<tr>
      <td>${escapeHtml(run.test_run_id)}</td>
      <td>${escapeHtml(run.record_environment || "test")}</td>
      <td>${escapeHtml(run.cluster_count || 0)}</td>
      <td>${escapeHtml(run.article_count || 0)}</td>
      <td>${escapeHtml(run.latest_article_at || "n/a")}</td>
    </tr>`).join("");
  }

  function renderError(error) {
    const detail = error.detail ? JSON.stringify(error.detail, null, 2) : "";
    return `<strong>${escapeHtml(error.stage || "Error")}: ${escapeHtml(error.message || error.summary || "Request failed")}</strong>
      <div>Request ID: ${escapeHtml(error.requestId || error.request_id || "unavailable")}</div>
      ${detail ? `<details><summary>Technical detail</summary><pre>${escapeHtml(detail)}</pre></details>` : ""}`;
  }

  window.NewsRenderers = {
    escapeHtml,
    metric,
    number,
    upper,
    renderEventSummary,
    renderPipeline,
    renderImpacts,
    renderSignal,
    renderEvidence,
    renderCluster,
    renderSources,
    renderSourceFilings,
    renderRecent,
    renderTestRuns,
    renderError
  };
})();
