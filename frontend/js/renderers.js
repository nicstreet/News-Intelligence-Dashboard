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

  function percent(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "n/a";
    }
    const numeric = Number(value) * 100;
    const prefix = numeric > 0 ? "+" : "";
    return `${prefix}${numeric.toFixed(2)}%`;
  }

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (bytes < 1024) return `${bytes.toFixed(0)} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1048576).toFixed(2)} MB`;
    return `${(bytes / 1073741824).toFixed(2)} GB`;
  }

  function upper(value) {
    return String(value || "n/a").replaceAll("_", " ").toUpperCase();
  }

  function ukDateTime(value) {
    if (!value) {
      return {date: "n/a", time: "n/a"};
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return {date: "n/a", time: "n/a"};
    }
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/London",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false
    }).formatToParts(date);
    const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return {
      date: `${byType.day}/${byType.month}/${byType.year}`,
      time: `${byType.hour}:${byType.minute}:${byType.second}`
    };
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

  function renderCompactImpacts(impacts) {
    if (!impacts || impacts.length === 0) {
      return `<tr><td colspan="7">No instrument impacts available.</td></tr>`;
    }
    return impacts.map((impact) => `<tr>
      <td>${escapeHtml(impact.symbol)}</td>
      <td>${escapeHtml(impact.entity_type)}</td>
      <td>${escapeHtml(impact.relationship)}</td>
      <td class="direction-${upper(impact.direction)}">${upper(impact.direction)}</td>
      <td>${number(impact.directional_strength, 2)}</td>
      <td>${number(impact.relevance, 2)}</td>
      <td>${number(impact.confidence, 2)}</td>
    </tr>`).join("");
  }

  function renderSignal(signal) {
    if (!signal) {
      return `<div class="metric"><span>Status</span><strong>No signal generated.</strong></div>`;
    }
    const metrics = signal.signal || {};
    const decision = signal.decision || {};
    const direction = upper(metrics.direction || "neutral");
    return `<div class="signal-hero">
      <div>
        <div class="kv-label">News signal score</div>
        <div class="big-score direction-${direction}">${number(metrics.signal_score, 1)}</div>
      </div>
      <div class="action-pill action-${direction}">${direction}</div>
    </div>
    <div class="signal-grid">
      ${metric("Instrument", signal.instrument ? signal.instrument.symbol : "n/a")}
      ${metric("Score band", upper(metrics.strength || "neutral"))}
      ${metric("Direction", direction, `direction-${direction}`)}
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
      <td>${escapeHtml(source.current_status)}${source.stale ? " / STALE" : ""}${source.due ? " / DUE" : ""}</td>
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

  function renderRecent(events, selectedEventId) {
    if (!events || events.length === 0) {
      return `<tr><td colspan="8">No recent events available.</td></tr>`;
    }
    return events.map((event) => `<tr data-event-id="${escapeHtml(event.event_id)}" class="${event.event_id === selectedEventId ? "active-row" : ""}">
      <td>${escapeHtml(event.timestamps ? event.timestamps.processed_at : "n/a")}</td>
      <td>${upper(event.event_type)}</td>
      <td>${escapeHtml(event.primary_symbol || "n/a")}</td>
      <td>${escapeHtml(event.headline)}</td>
      <td class="direction-${upper(event.analysis ? event.analysis.direction : "neutral")}">${upper(event.analysis ? event.analysis.direction : "neutral")}</td>
      <td>${number(event.analysis ? event.analysis.confidence : null, 2)}</td>
      <td>${sourceLink(event)}</td>
      <td>${escapeHtml(event.cluster_id || "n/a")}</td>
    </tr>`).join("");
  }

  function renderEventRows(events, selectedEventId) {
    if (!events || events.length === 0) {
      return `<tr><td colspan="10">No recent events available.</td></tr>`;
    }
    return events.map((event) => {
      const analysis = event.analysis || {};
      const published = ukDateTime(event.timestamps ? event.timestamps.published_at : null);
      return `<tr data-event-id="${escapeHtml(event.event_id)}" class="${event.event_id === selectedEventId ? "active-row" : ""}">
        <td>${eventIdSourceLink(event)}</td>
        <td>${escapeHtml(published.date)}</td>
        <td>${escapeHtml(published.time)}</td>
        <td>${escapeHtml(event.headline)}</td>
        <td>${upper(event.event_type)}</td>
        <td>${escapeHtml(symbolSpecificValue(event))}</td>
        <td class="direction-${upper(analysis.direction || "neutral")}">${upper(analysis.direction || "neutral")}</td>
        <td>${number(analysis.directional_strength, 2)}</td>
        <td>${number(analysis.confidence, 2)}</td>
        <td>${number(analysis.quality, 2)}</td>
      </tr>`;
    }).join("");
  }

  function renderSidebarWatch(events) {
    if (!events || events.length === 0) {
      return `<div class="tick-row">
        <span class="row-left">
          <span class="row-icon" data-fallback="--"></span>
          <span class="row-main">
            <span class="row-title">No recent events</span>
            <span class="row-sub">Refresh or run source polling</span>
          </span>
        </span>
        <span class="row-metric">0</span>
      </div>`;
    }
    return events.slice(0, 5).map((event) => {
      const analysis = event.analysis || {};
      const direction = String(analysis.direction || "neutral").toLowerCase();
      const className = direction === "bullish" ? "up" : direction === "bearish" ? "down" : "neutral";
      const fallback = direction === "bullish" ? "+" : direction === "bearish" ? "-" : "=";
      return `<div class="tick-row" data-event-id="${escapeHtml(event.event_id)}">
        <span class="row-left">
          <span class="row-icon ${className}" data-fallback="${escapeHtml(fallback)}"></span>
          <span class="row-main">
            <span class="row-title">${escapeHtml(event.primary_symbol || event.event_type || "Market event")}</span>
            <span class="row-sub">${escapeHtml(event.headline || "No headline")}</span>
          </span>
        </span>
        <span class="row-metric ${className}">${number(analysis.directional_strength, 2)}</span>
      </div>`;
    }).join("");
  }

  function eventIdSourceLink(event) {
    const source = event && event.source ? event.source : {};
    const eventId = event && event.event_id ? event.event_id : "n/a";
    if (!source.source_url) {
      return escapeHtml(eventId);
    }
    return `<a href="${escapeHtml(source.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(eventId)}</a>`;
  }

  function symbolSpecificValue(event) {
    const scope = String(event && event.event_scope ? event.event_scope : "").toLowerCase();
    if (!["instrument", "etf"].includes(scope)) {
      return "N/A";
    }
    return event.primary_symbol || "N/A";
  }

  function sourceLink(event) {
    const source = event && event.source ? event.source : {};
    const sourceName = source.source_name || "n/a";
    if (!source.source_url) {
      return escapeHtml(sourceName);
    }
    return `<a href="${escapeHtml(source.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceName)}</a>`;
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

  function renderAutomation(status) {
    if (!status) {
      return `<p>No automation status available.</p>`;
    }
    const sources = status.sources || [];
    const rows = sources.length
      ? sources.map((source) => `<tr>
        <td>${escapeHtml(source.source_name)}</td>
        <td>${escapeHtml(source.connector_type)}</td>
        <td>${escapeHtml(source.current_status)}</td>
        <td>${String(Boolean(source.due)).toUpperCase()}</td>
        <td>${String(Boolean(source.stale)).toUpperCase()}</td>
        <td>${escapeHtml(source.items_ingested || 0)}</td>
        <td>${escapeHtml(source.last_successful_ingestion || "n/a")}</td>
        <td>${escapeHtml(source.last_polled_at || "n/a")}</td>
        <td>${escapeHtml(source.next_poll_after || "n/a")}</td>
        <td>${escapeHtml(source.last_failure || "n/a")}</td>
      </tr>`).join("")
      : `<tr><td colspan="10">No source automation status available.</td></tr>`;
    const background = status.background || {};
    const recentRuns = status.recent_runs || [];
    return `<div class="metric-grid">
      ${metric("Automation enabled", String(Boolean(status.enabled)).toUpperCase())}
      ${metric("Background running", String(Boolean(background.running)).toUpperCase())}
      ${metric("Interval seconds", background.interval_seconds || status.scheduler_interval_seconds || "n/a")}
      ${metric("Due sources", status.due_count || 0)}
      ${metric("Stale sources", status.stale_count || 0)}
      ${metric("Retention due", String(Boolean(status.retention && status.retention.due)).toUpperCase())}
      ${metric("Generated", status.generated_at || "n/a")}
      ${metric("Last tick", background.last_tick_at || "n/a")}
      ${metric("Next tick", background.next_tick_at || "n/a")}
      ${metric("Last error", background.last_error || "none")}
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Source</th>
            <th>Connector</th>
            <th>Status</th>
            <th>Due</th>
            <th>Stale</th>
            <th>Items</th>
            <th>Last success</th>
            <th>Last poll</th>
            <th>Next poll</th>
            <th>Last failure</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="table-wrap automation-runs">
      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>Reason</th>
            <th>Completed</th>
            <th>Sources</th>
            <th>Fetched</th>
            <th>Ingested</th>
            <th>Skipped</th>
            <th>Errors</th>
            <th>Retention</th>
          </tr>
        </thead>
        <tbody>${renderAutomationRuns(recentRuns)}</tbody>
      </table>
    </div>`;
  }

  function renderAutomationRuns(runs) {
    if (!runs || runs.length === 0) {
      return `<tr><td colspan="9">No automation runs recorded.</td></tr>`;
    }
    return runs.map((run) => `<tr>
      <td>${escapeHtml(run.automation_run_id || "n/a")}</td>
      <td>${escapeHtml(run.reason || "n/a")}</td>
      <td>${escapeHtml(run.completed_at || "n/a")}</td>
      <td>${escapeHtml(run.source_run_count || 0)}</td>
      <td>${escapeHtml(run.fetched_count || 0)}</td>
      <td>${escapeHtml(run.ingested_count || 0)}</td>
      <td>${escapeHtml(run.skipped_count || 0)}</td>
      <td>${escapeHtml(run.error_count || 0)}</td>
      <td>${String(Boolean(run.retention_applied)).toUpperCase()}</td>
    </tr>`).join("");
  }

  function renderUniverseSummary(universe) {
    const instruments = universe && universe.instruments ? universe.instruments : [];
    const lseCount = instruments.filter((instrument) => instrument.uk_lse_gbp_etf).length;
    const themes = new Set(instruments.map((instrument) => instrument.primary_theme).filter(Boolean));
    return [
      metric("Universe version", universe ? universe.version : "n/a"),
      metric("Instruments", instruments.length),
      metric("Themes", themes.size),
      metric("UK LSE GBP ETFs", lseCount)
    ].join("");
  }

  function renderUniverseTable(universe) {
    const instruments = universe && universe.instruments ? universe.instruments : [];
    if (instruments.length === 0) {
      return `<tr><td colspan="9">No favourites configured.</td></tr>`;
    }
    return instruments.map((instrument) => `<tr>
      <td>${escapeHtml(instrument.symbol)}</td>
      <td>${escapeHtml(instrument.name)}</td>
      <td>${escapeHtml(instrument.instrument_type)}</td>
      <td>${escapeHtml(instrument.exchange)}</td>
      <td>${escapeHtml(instrument.currency)}</td>
      <td>${escapeHtml(instrument.primary_theme)}</td>
      <td>${escapeHtml(instrument.sub_theme)}</td>
      <td>${escapeHtml(instrument.overlap_group)}</td>
      <td>${escapeHtml(instrument.benchmark || "n/a")}</td>
    </tr>`).join("");
  }

  function renderCalibrationSummary(report) {
    if (!report) {
      return metric("Status", "No calibration report loaded");
    }
    return [
      metric("Universe version", report.universe_version || "n/a"),
      metric("Favourite count", report.favourites_count || 0),
      metric("Signals in scope", report.signal_count || 0),
      metric("Outcome status", upper(report.outcome_status || "unknown"))
    ].join("");
  }

  function renderCalibrationReport(report) {
    if (!report) {
      return `<p>No calibration report loaded.</p>`;
    }
    const profiles = report.profiles || [];
    const rows = profiles.length
      ? profiles.map((profile) => `<tr>
        <td>${escapeHtml(profile.calibration_profile)}</td>
        <td>${escapeHtml(profile.sample_size)}</td>
        <td>${number(profile.mean_signal_score, 2)}</td>
        <td>${escapeHtml(profile.status)}</td>
      </tr>`).join("")
      : `<tr><td colspan="4">No calibration profiles available yet.</td></tr>`;
    return `<div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Profile</th>
            <th>Sample</th>
            <th>Mean score</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  function renderCalibrationOutcomeSummary(outcomes) {
    if (!outcomes) {
      return metric("Joined outcomes", "Not loaded");
    }
    return [
      metric("Joined outcomes", outcomes.outcome_count || 0),
      metric("Signals checked", outcomes.signal_count || 0),
      metric("Missing market data", outcomes.missing_market_data_count || 0),
      metric("Join status", upper(outcomes.outcome_status || "unknown"))
    ].join("");
  }

  function renderCalibrationOutcomes(outcomes) {
    const rows = outcomes && outcomes.rows ? outcomes.rows : [];
    if (rows.length === 0) {
      return `<tr><td colspan="12">No joined news-vs-market outcomes available. Cache EODHD bars for event symbols, then refresh.</td></tr>`;
    }
    return rows.map((row) => {
      const returns = row.returns || {};
      const abnormal = row.abnormal_returns || {};
      const dateTime = ukDateTime(row.event_time);
      return `<tr>
        <td>${escapeHtml(row.event_id || "n/a")}</td>
        <td>${escapeHtml(`${dateTime.date} ${dateTime.time}`)}</td>
        <td>${escapeHtml(row.symbol || "n/a")}</td>
        <td>${upper(row.event_type)}</td>
        <td>${number(row.signal_score, 1)}</td>
        <td>${upper(row.market_session || row.anchor_source || "n/a")}</td>
        <td>${number(row.price_at_event, 2)}</td>
        <td class="${returnClass(returns["30m"])}">${percent(returns["30m"])}</td>
        <td class="${returnClass(returns["1d"])}">${percent(returns["1d"])}</td>
        <td class="${returnClass(returns["5d"])}">${percent(returns["5d"])}</td>
        <td class="${returnClass(abnormal["1d"])}">${percent(abnormal["1d"])}</td>
        <td>${upper(row.outcome_status)}</td>
      </tr>`;
    }).join("");
  }

  function renderFinalIntelligenceRows(output) {
    const records = output && output.records ? output.records : [];
    if (records.length === 0) {
      return `<tr><td colspan="10">No clean intelligence records available yet. The app will update sources and export deltas automatically.</td></tr>`;
    }
    return records.map((record) => {
      const instrument = record.instrument || {};
      const signal = record.signal || {};
      const market = record.market_reaction || {};
      const returns = market.returns || {};
      const abnormal = market.abnormal_returns || {};
      const exportStatus = record.export_status || {};
      const dateTime = ukDateTime(record.event_time);
      return `<tr>
        <td>${escapeHtml(`${dateTime.date} ${dateTime.time}`)}</td>
        <td>${escapeHtml(instrument.symbol || "n/a")}</td>
        <td>${escapeHtml(record.headline || "n/a")}</td>
        <td>${upper(record.event_type)}</td>
        <td class="${directionClass(signal.direction)}">${upper(signal.direction)} ${number(signal.signal_score, 1)}</td>
        <td>${number(signal.confidence, 2)}</td>
        <td class="${returnClass(returns["1d"])}">${percent(returns["1d"])}</td>
        <td class="${returnClass(abnormal["1d"])}">${percent(abnormal["1d"])}</td>
        <td>${upper(market.outcome_status || "pending")}</td>
        <td>${exportStatus.exported ? escapeHtml(exportStatus.path || "exported") : "pending"}</td>
      </tr>`;
    }).join("");
  }

  function renderRunProgress(progress) {
    if (!progress || progress.status === "idle") {
      return `<div class="progress-shell muted-text">No active run.</div>`;
    }
    const connectorIndex = Number(progress.connector_index || 0);
    const connectorTotal = Number(progress.connector_total || 0);
    const recordIndex = Number(progress.record_index || 0);
    const recordTotal = Number(progress.record_total || 0);
    const symbolIndex = Number(progress.market_symbol_index || 0);
    const symbolTotal = Number(progress.market_symbol_total || 0);
    const connectorLabel = progress.connector_name
      ? `${escapeHtml(progress.connector_name)} (${connectorIndex || 0} of ${connectorTotal || 0})`
      : "Connector n/a";
    const recordLabel = recordTotal > 0
      ? `Record ${recordIndex || 0} of ${recordTotal}`
      : "Record n/a";
    const marketLabel = symbolTotal > 0
      ? `Market data ${escapeHtml(progress.market_symbol || "n/a")} (${symbolIndex} of ${symbolTotal})`
      : "Market data n/a";
    const percentComplete = runProgressPercent(progress);
    return `<div class="progress-shell">
      <div class="progress-topline">
        <strong>${upper(progress.status)}</strong>
        <span>${upper(progress.phase)}</span>
        <span>${escapeHtml(progress.message || "")}</span>
      </div>
      <div class="progress-track" aria-label="Run progress">
        <span class="progress-fill" style="width: ${percentComplete}%"></span>
      </div>
      <div class="progress-grid">
        ${metric("Connector", connectorLabel)}
        ${metric("Record", recordLabel)}
        ${metric("Market data", marketLabel)}
        ${metric("Counts", `${progress.ingested_count || 0} ingested / ${progress.exported_count || 0} exported`)}
      </div>
    </div>`;
  }

  function runProgressPercent(progress) {
    if (progress.status === "complete") return 100;
    if (progress.status === "error") return 100;
    const recordTotal = Number(progress.record_total || 0);
    const recordIndex = Number(progress.record_index || 0);
    if (recordTotal > 0) {
      return Math.max(4, Math.min(95, Math.round((recordIndex / recordTotal) * 100)));
    }
    const connectorTotal = Number(progress.connector_total || 0);
    const connectorIndex = Number(progress.connector_index || 0);
    if (connectorTotal > 0) {
      return Math.max(4, Math.min(80, Math.round((connectorIndex / connectorTotal) * 100)));
    }
    return progress.status === "running" ? 12 : 0;
  }

  function directionClass(direction) {
    const value = upper(direction);
    if (value === "LONG" || value === "BULLISH") return "direction-BULLISH";
    if (value === "SHORT" || value === "BEARISH") return "direction-BEARISH";
    return "direction-NEUTRAL";
  }

  function returnClass(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "";
    }
    if (Number(value) > 0) return "direction-BULLISH";
    if (Number(value) < 0) return "direction-BEARISH";
    return "direction-NEUTRAL";
  }

  function renderFileDropStatus(status) {
    if (!status) {
      return metric("Status", "No file-drop status loaded");
    }
    return [
      metric("Enabled", String(Boolean(status.enabled)).toUpperCase()),
      metric("Schema", status.schema_version || "n/a"),
      metric("Output dir exists", String(Boolean(status.output_dir_exists)).toUpperCase()),
      metric("Output dir", status.output_dir || "n/a")
    ].join("");
  }

  function renderMarketDataSummary(coverage) {
    if (!coverage) {
      return metric("Coverage", "No market-data coverage loaded");
    }
    const missing = coverage.missing_configured_symbols || [];
    const range = coverage.first_timestamp_utc && coverage.last_timestamp_utc
      ? `${dateOnly(coverage.first_timestamp_utc)} to ${dateOnly(coverage.last_timestamp_utc)}`
      : "n/a";
    return [
      metric("Covered symbols", coverage.covered_symbol_count || 0),
      metric("Configured symbols", coverage.configured_symbol_count || 0),
      metric("Cached bars", coverage.total_bar_count || 0),
      metric("Missing configured symbols", missing.length),
      metric("Date range", range),
      metric("Provider", coverage.provider || "n/a"),
      metric("Coverage rows", coverage.record_count || 0),
      metric("Missing symbols", missing.slice(0, 6).join(", ") || "none")
    ].join("");
  }

  function renderMarketCoverage(coverage) {
    const rows = coverage && coverage.rows ? coverage.rows : [];
    if (rows.length === 0) {
      return `<tr><td colspan="10">No cached market-data coverage available.</td></tr>`;
    }
    return [...rows]
      .sort((left, right) => String(left.symbol).localeCompare(String(right.symbol)))
      .map((row) => `<tr>
        <td>${escapeHtml(row.symbol || "n/a")}</td>
        <td>${escapeHtml(row.exchange || "n/a")}</td>
        <td>${escapeHtml(row.interval || "n/a")}</td>
        <td>${number(row.bar_count, 0)}</td>
        <td>${escapeHtml(dateOnly(row.first_timestamp_utc))}</td>
        <td>${escapeHtml(dateOnly(row.last_timestamp_utc))}</td>
        <td>${number(row.latest_adjusted_close ?? row.latest_close, 2)}</td>
        <td>${number(row.latest_volume, 0)}</td>
        <td>${escapeHtml(dateOnly(row.last_request_at))}</td>
        <td>${escapeHtml(upper(row.last_request_status || "n/a"))}</td>
      </tr>`).join("");
  }

  function renderMarketMappingSummary(mappings) {
    if (!mappings) {
      return metric("Mappings", "No market-data mappings loaded");
    }
    const failures = mappings.recent_failures || [];
    const unresolved = failures.filter(
      (item) => item.mapping_status === "default_us_suffix"
        && item.failure_kind === "provider_not_found"
    );
    return [
      metric("Mapping file", mappings.mapping_file || "n/a"),
      metric("Provider overrides", (mappings.symbol_overrides || []).length),
      metric("Exchange suffixes", (mappings.exchange_suffixes || []).length),
      metric("Recent failed symbols", failures.length),
      metric("Likely unmapped", unresolved.length),
      metric("Provider", mappings.provider || "n/a")
    ].join("");
  }

  function renderMarketOverrides(mappings) {
    const rows = mappings && mappings.symbol_overrides ? mappings.symbol_overrides : [];
    if (rows.length === 0) {
      return `<tr><td colspan="3">No provider overrides configured.</td></tr>`;
    }
    return rows.map((row) => `<tr>
      <td>${escapeHtml(row.symbol || "n/a")}</td>
      <td>${escapeHtml(row.provider_symbol || "n/a")}</td>
      <td>${escapeHtml(upper(row.mapping_type || "n/a"))}</td>
    </tr>`).join("");
  }

  function renderMarketMappingFailures(mappings) {
    const rows = mappings && mappings.recent_failures ? mappings.recent_failures : [];
    if (rows.length === 0) {
      return `<tr><td colspan="5">No recent market-data mapping failures.</td></tr>`;
    }
    return rows.map((row) => `<tr>
      <td>${escapeHtml(dateOnly(row.requested_at))}</td>
      <td>${escapeHtml(row.symbol || "n/a")}</td>
      <td>${escapeHtml(row.exchange || "n/a")}</td>
      <td>${escapeHtml(row.current_provider_symbol || "n/a")}</td>
      <td>${escapeHtml(upper(row.mapping_status || row.failure_kind || "n/a"))}</td>
    </tr>`).join("");
  }

  function renderMarketBars(bars) {
    if (!bars || bars.length === 0) {
      return `<tr><td colspan="9">No cached market bars available.</td></tr>`;
    }
    return bars.map((bar) => `<tr>
      <td>${escapeHtml(bar.timestamp_utc || "n/a")}</td>
      <td>${escapeHtml(bar.symbol || "n/a")}</td>
      <td>${escapeHtml(bar.exchange || "n/a")}</td>
      <td>${escapeHtml(bar.interval || "n/a")}</td>
      <td>${number(bar.open, 2)}</td>
      <td>${number(bar.high, 2)}</td>
      <td>${number(bar.low, 2)}</td>
      <td>${number(bar.close, 2)}</td>
      <td>${number(bar.volume, 0)}</td>
    </tr>`).join("");
  }

  function renderMarketRequests(requests) {
    if (!requests || requests.length === 0) {
      return `<tr><td colspan="7">No market-data requests recorded.</td></tr>`;
    }
    return requests.map((request) => `<tr>
      <td>${escapeHtml(request.requested_at || "n/a")}</td>
      <td>${escapeHtml(request.symbol || "n/a")}</td>
      <td>${escapeHtml(request.interval || "n/a")}</td>
      <td>${escapeHtml(request.status || "n/a")}</td>
      <td>${escapeHtml(request.records_returned || 0)}</td>
      <td>${escapeHtml(request.records_stored || 0)}</td>
      <td>${escapeHtml(request.estimated_api_call_cost || 0)}</td>
    </tr>`).join("");
  }

  function dateOnly(value) {
    if (!value) {
      return "n/a";
    }
    return String(value).split("T")[0];
  }

  function renderStorageSummary(storage, retention) {
    if (!storage) {
      return metric("Status", "No storage summary loaded");
    }
    const layers = storage.layers || [];
    const currentBytes = layers.reduce((total, layer) => total + Number(layer.current_bytes || 0), 0);
    const projectedBytes = layers.reduce(
      (total, layer) => total + storageProjectedBytes(layer, retention),
      0
    );
    return [
      metric("Current JSON payloads", formatBytes(currentBytes)),
      metric("Projected retention", formatBytes(projectedBytes)),
      metric("SQLite database file", formatBytes(storage.database_file_bytes || 0)),
      metric("Storage layers", layers.length),
      metric("Retention profile", storage.retention_version || "n/a"),
      metric("Generated", storage.generated_at || "n/a")
    ].join("");
  }

  function renderStorageVisualisation(storage, retention) {
    const layers = storage && storage.layers ? storage.layers : [];
    if (layers.length === 0) {
      return `<p>No storage layers available.</p>`;
    }
    const maxBytes = Math.max(
      1,
      ...layers.flatMap((layer) => [
        Number(layer.current_bytes || 0),
        storageProjectedBytes(layer, retention)
      ])
    );
    return layers.map((layer) => {
      const currentBytes = Number(layer.current_bytes || 0);
      const projectedBytes = storageProjectedBytes(layer, retention);
      const currentWidth = Math.max(1, (currentBytes / maxBytes) * 100);
      const projectedWidth = Math.max(1, (projectedBytes / maxBytes) * 100);
      return `<div class="storage-bar-row">
        <div class="storage-bar-label">${escapeHtml(layer.layer_name || layer.layer_key)}</div>
        <div class="storage-bar-track" aria-label="${escapeHtml(layer.layer_name || layer.layer_key)} projected storage">
          <span class="storage-bar-fill projected" style="width: ${projectedWidth}%"></span>
          <span class="storage-bar-fill current" style="width: ${currentWidth}%"></span>
        </div>
        <div class="storage-bar-value">${escapeHtml(formatBytes(projectedBytes))}</div>
      </div>`;
    }).join("");
  }

  function renderStorageLayers(storage, retention) {
    const layers = storage && storage.layers ? storage.layers : [];
    if (layers.length === 0) {
      return `<tr><td colspan="7">No storage layers available.</td></tr>`;
    }
    return layers.map((layer) => {
      const projectedBytes = storageProjectedBytes(layer, retention);
      const retentionCell = layer.adjustable
        ? retentionSlider(layer, retention)
        : `<span class="muted-text">Permanent / audit</span>`;
      return `<tr>
        <td>${escapeHtml(layer.layer_name || layer.layer_key)}</td>
        <td>${escapeHtml(layer.description || "")}</td>
        <td>
          <strong>${escapeHtml(formatBytes(layer.current_bytes))}</strong>
          <div class="meta-text">${escapeHtml(layer.record_count || 0)} records</div>
        </td>
        <td>${escapeHtml(layer.days_worth || 0)}</td>
        <td>${escapeHtml(layer.ticker_count || 0)}</td>
        <td>${retentionCell}</td>
        <td>
          <strong>${escapeHtml(formatBytes(projectedBytes))}</strong>
          <div class="meta-text">${escapeHtml(formatBytes(layer.estimated_bytes_per_day || 0))} / day</div>
        </td>
      </tr>`;
    }).join("");
  }

  function retentionSlider(layer, retention) {
    const days = activeRetentionDays(layer, retention);
    return `<div class="retention-control">
      <input type="range" min="7" max="3650" step="7" value="${days}" data-retention-layer="${escapeHtml(layer.layer_key)}" aria-label="${escapeHtml(layer.layer_name || layer.layer_key)} retention days">
      <span>${escapeHtml(days)} days</span>
    </div>`;
  }

  function activeRetentionDays(layer, retention) {
    const configured = retention && Object.hasOwn(retention, layer.layer_key)
      ? Number(retention[layer.layer_key])
      : Number(layer.retention_days || 365);
    if (Number.isNaN(configured) || configured < 7) return 7;
    return Math.round(configured);
  }

  function storageProjectedBytes(layer, retention) {
    if (!layer || !layer.adjustable) {
      return Number(layer ? layer.current_bytes || 0 : 0);
    }
    const perDay = Number(layer.estimated_bytes_per_day || 0);
    if (perDay <= 0) {
      return Number(layer.current_bytes || 0);
    }
    return Math.round(perDay * activeRetentionDays(layer, retention));
  }

  function renderRetentionPlan(plan) {
    if (!plan) {
      return "";
    }
    const layers = plan.layers || [];
    const rows = layers.length
      ? layers.map((layer) => `<tr>
        <td>${escapeHtml(layer.layer_name || layer.layer_key)}</td>
        <td>${layer.adjustable ? `${escapeHtml(layer.retention_days || "n/a")} days` : "Permanent / audit"}</td>
        <td>${escapeHtml(layer.cutoff_at || "n/a")}</td>
        <td>${escapeHtml(layer.candidate_records || 0)}</td>
        <td>${escapeHtml(formatBytes(layer.candidate_bytes || 0))}</td>
        <td>${escapeHtml(layer.skipped_production_records || 0)}</td>
        <td>${escapeHtml(layer.skipped_missing_timestamp_records || 0)}</td>
        <td>${escapeHtml(layer.deleted_records || 0)}</td>
      </tr>`).join("")
      : `<tr><td colspan="8">No retention layers available.</td></tr>`;
    const mode = String(plan.mode || "dry_run").replaceAll("_", " ").toUpperCase();
    return `<section class="retention-preview">
      <div class="metric-grid">
        ${metric("Retention mode", mode)}
        ${metric("Eligible records", plan.total_candidate_records || 0)}
        ${metric("Eligible storage", formatBytes(plan.total_candidate_bytes || 0))}
        ${metric("Deleted records", plan.total_deleted_records || 0)}
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Layer</th>
              <th>Retention</th>
              <th>Cutoff</th>
              <th>Eligible</th>
              <th>Bytes</th>
              <th>Production skipped</th>
              <th>No timestamp</th>
              <th>Deleted</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>`;
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
    formatBytes,
    upper,
    renderEventSummary,
    renderPipeline,
    renderImpacts,
    renderCompactImpacts,
    renderSignal,
    renderEvidence,
    renderCluster,
    renderSources,
    renderSourceFilings,
    renderRecent,
    renderEventRows,
    renderSidebarWatch,
    renderTestRuns,
    renderAutomation,
    renderUniverseSummary,
    renderUniverseTable,
    renderCalibrationSummary,
    renderCalibrationReport,
    renderCalibrationOutcomeSummary,
    renderCalibrationOutcomes,
    renderFinalIntelligenceRows,
    renderRunProgress,
    renderFileDropStatus,
    renderMarketDataSummary,
    renderMarketCoverage,
    renderMarketMappingSummary,
    renderMarketOverrides,
    renderMarketMappingFailures,
    renderMarketBars,
    renderMarketRequests,
    renderStorageSummary,
    renderStorageVisualisation,
    renderStorageLayers,
    renderRetentionPlan,
    renderError
  };
})();
