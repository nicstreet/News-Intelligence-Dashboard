(function () {
  const baseFixtures = [
    {
      id: "nvda_earnings_beat_raise",
      label: "NVDA earnings beat and raised guidance",
      items: [{
        headline: "NVIDIA reports earnings above expectations and raises guidance",
        body: "Revenue and earnings exceeded expectations and forward guidance was increased.",
        source_name: "Example Newswire",
        source_type: "newswire",
        source_url: "https://example.test/nvda-earnings",
        published_at: "2026-07-11T09:14:00Z",
        known_ticker: "NVDA",
        source_article_id: "nvda-earnings-001"
      }]
    },
    {
      id: "amd_beat_guidance_reduced",
      label: "AMD earnings beat but guidance reduced",
      items: [{
        headline: "AMD beats earnings but cuts guidance for the next quarter",
        body: "Historic earnings beat expectations, but management reduced forward guidance.",
        source_name: "Example Newswire",
        source_type: "newswire",
        published_at: "2026-07-11T09:20:00Z",
        known_ticker: "AMD",
        source_article_id: "amd-guidance-001"
      }]
    },
    {
      id: "aapl_anticipated_product",
      label: "AAPL product announcement already anticipated",
      items: [{
        headline: "Apple announces anticipated product launch at developer event",
        body: "The product update had been widely expected by analysts.",
        source_name: "Company Press Release",
        source_type: "company",
        published_at: "2026-07-11T09:30:00Z",
        known_ticker: "AAPL",
        source_article_id: "aapl-product-001"
      }]
    },
    {
      id: "xom_profit_warning",
      label: "XOM company-specific profit warning",
      items: [{
        headline: "Exxon issues profit warning and cuts outlook after refining weakness",
        body: "The company warned profits would be below prior expectations.",
        source_name: "Example Newswire",
        source_type: "newswire",
        published_at: "2026-07-11T09:40:00Z",
        known_ticker: "XOM",
        source_article_id: "xom-warning-001"
      }]
    },
    {
      id: "unexpected_rate_cut",
      label: "Unexpected rate cut",
      items: [{
        headline: "Central bank announces unexpected rate cut at unscheduled meeting",
        body: "The surprise rate cut improved growth equity sentiment while pressuring bank margin assumptions.",
        source_name: "Central Bank Feed",
        source_type: "central_bank",
        published_at: "2026-07-11T10:00:00Z",
        country: "US",
        source_article_id: "fed-cut-001"
      }]
    },
    {
      id: "mrna_restricted_approval",
      label: "MRNA regulatory approval with restrictions",
      items: [{
        headline: "Moderna wins approval with label restrictions for respiratory vaccine",
        body: "Regulators granted approval with additional monitoring conditions and label warnings.",
        source_name: "Regulatory Feed",
        source_type: "regulatory",
        published_at: "2026-07-11T10:10:00Z",
        known_ticker: "MRNA",
        source_article_id: "mrna-approval-001"
      }]
    },
    {
      id: "boeing_safety_investigation",
      label: "Boeing safety investigation",
      items: [{
        headline: "Regulator opens safety investigation into Boeing 737 programme",
        body: "The safety investigation follows new quality-control concerns.",
        source_name: "Regulatory Feed",
        source_type: "regulatory",
        published_at: "2026-07-11T10:20:00Z",
        known_ticker: "BA",
        source_article_id: "ba-probe-001"
      }]
    },
    {
      id: "cameco_mine_disruption",
      label: "Cameco mine disruption",
      items: [{
        headline: "Cameco mine disruption tightens uranium supply outlook",
        body: "The disruption is expected to reduce Cameco output but support uranium market pricing.",
        source_name: "Example Newswire",
        source_type: "newswire",
        published_at: "2026-07-11T10:30:00Z",
        known_ticker: "CCJ",
        source_article_id: "ccj-mine-001"
      }]
    },
    {
      id: "takeover_rumour_then_confirmation",
      label: "Unconfirmed takeover rumour followed by confirmation",
      items: [
        {
          headline: "Apple subject of takeover rumour after approach from private consortium",
          body: "Market chatter suggested an approach, but no terms were confirmed.",
          source_name: "Market Blog",
          source_type: "blog",
          published_at: "2026-07-11T10:40:00Z",
          known_ticker: "AAPL",
          source_article_id: "aapl-rumour-001"
        },
        {
          headline: "Apple confirms acquisition bid from private consortium",
          body: "The company confirmed it received a preliminary acquisition bid.",
          source_name: "Company Press Release",
          source_type: "company",
          published_at: "2026-07-11T11:10:00Z",
          known_ticker: "AAPL",
          source_article_id: "aapl-confirmed-001"
        }
      ]
    },
    {
      id: "duplicate_syndicated_stories",
      label: "Duplicate syndicated stories",
      repeat: 20,
      items: [{
        headline: "NVIDIA reports earnings above expectations and raises guidance",
        body: "Revenue and earnings exceeded expectations and forward guidance was increased.",
        source_name: "Example Newswire",
        source_type: "newswire",
        published_at: "2026-07-11T09:14:00Z",
        known_ticker: "NVDA",
        source_article_id: "nvda-duplicate-base"
      }]
    },
    {
      id: "initial_report_then_denial",
      label: "Initial report followed by company denial",
      items: [
        {
          headline: "Apple subject of takeover rumour after approach from private consortium",
          body: "The report said the company had received informal interest.",
          source_name: "Market Blog",
          source_type: "blog",
          published_at: "2026-07-11T10:40:00Z",
          known_ticker: "AAPL",
          source_article_id: "aapl-rumour-denial-001"
        },
        {
          headline: "Apple denies takeover report and says no discussions are active",
          body: "The company denial contradicted the earlier takeover report.",
          source_name: "Company Press Release",
          source_type: "company",
          published_at: "2026-07-11T11:30:00Z",
          known_ticker: "AAPL",
          source_article_id: "aapl-denial-001"
        }
      ]
    },
    {
      id: "positive_news_rejected_by_price_action",
      label: "Positive news rejected by price action",
      items: [{
        headline: "NVIDIA shares fall despite positive product news as market rejects price action",
        body: "The price action rejected the positive announcement and closed below the prior support area.",
        source_name: "Example Newswire",
        source_type: "newswire",
        published_at: "2026-07-11T11:40:00Z",
        known_ticker: "NVDA",
        source_article_id: "nvda-rejected-001",
        metadata: {price_action_confirmation: "rejected"}
      }]
    }
  ];

  const relations = {
    NVDA: [["NVDA", "instrument", "direct", "instrument", 1, 1], ["SMH", "etf", "industry_exposure", "industry", 0.55, 0.5], ["XLK", "etf", "sector_exposure", "sector", 0.3, 0.35], ["QQQ", "etf", "index_constituent", "global_market", 0.2, 0.25], ["SPY", "etf", "index_constituent", "global_market", 0.08, 0.1]],
    AMD: [["AMD", "instrument", "direct", "instrument", 1, 1], ["SMH", "etf", "industry_exposure", "industry", 0.5, 0.48], ["XLK", "etf", "sector_exposure", "sector", 0.28, 0.33], ["QQQ", "etf", "index_constituent", "global_market", 0.18, 0.22], ["SPY", "etf", "index_constituent", "global_market", 0.07, 0.09]],
    AAPL: [["AAPL", "instrument", "direct", "instrument", 1, 1], ["XLK", "etf", "sector_exposure", "sector", 0.45, 0.45], ["QQQ", "etf", "index_constituent", "global_market", 0.32, 0.32], ["SPY", "etf", "index_constituent", "global_market", 0.18, 0.18]],
    XOM: [["XOM", "instrument", "direct", "instrument", 1, 1], ["XLE", "etf", "sector_exposure", "sector", 0.42, 0.4], ["SPY", "etf", "index_constituent", "global_market", 0.12, 0.12]],
    MRNA: [["MRNA", "instrument", "direct", "instrument", 1, 1], ["IBB", "etf", "industry_exposure", "industry", 0.48, 0.8], ["XLV", "etf", "sector_exposure", "sector", 0.26, 0.25], ["SPY", "etf", "index_constituent", "global_market", 0.07, 0.08]],
    BA: [["BA", "instrument", "direct", "instrument", 1, 1], ["ITA", "etf", "industry_exposure", "industry", 0.5, 0.45], ["XLI", "etf", "sector_exposure", "sector", 0.3, 0.28], ["SPY", "etf", "index_constituent", "global_market", 0.1, 0.1]],
    CCJ: [["CCJ", "instrument", "direct", "instrument", 1, 1], ["URA", "etf", "commodity_exposure", "commodity", 0.55, 0.45], ["SPY", "etf", "index_constituent", "global_market", 0.05, 0.05]]
  };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function fixtureItems(fixture) {
    if (!fixture.repeat) {
      return clone(fixture.items);
    }
    const items = [];
    for (let index = 0; index < fixture.repeat; index += 1) {
      const item = clone(fixture.items[0]);
      item.source_article_id = `${item.source_article_id}-${String(index).padStart(2, "0")}`;
      item.published_at = `2026-07-11T09:${String(14 + (index % 10)).padStart(2, "0")}:00Z`;
      items.push(item);
    }
    return items;
  }

  function classify(item) {
    const text = `${item.headline} ${item.body || ""}`.toLowerCase();
    if (text.includes("despite") && (text.includes("shares fall") || text.includes("price action rejected"))) {
      return ["market_structure", "positive_news_rejected_by_price", "confirmed", "bearish", -0.32, ["RISK_OVERLAY", "VETO"], "market_reaction"];
    }
    if (text.includes("denies")) {
      return ["rumour_unconfirmed", "company_denial", "denied", "neutral", -0.08, ["RISK_OVERLAY", "VETO"], "merger_acquisition"];
    }
    if (text.includes("confirms") && (text.includes("acquisition") || text.includes("bid"))) {
      return ["merger_acquisition", "acquisition_confirmed", "confirmed", "bullish", 0.64, ["CATALYST", "CONFIRMATION"], "merger_acquisition"];
    }
    if (text.includes("takeover rumour") || text.includes("approach from")) {
      return ["rumour_unconfirmed", "takeover_rumour", "unconfirmed", "bullish", 0.46, ["RISK_OVERLAY", "CONFIRMATION"], "merger_acquisition"];
    }
    if (text.includes("rate cut") && (text.includes("unexpected") || text.includes("surprise"))) {
      return ["central_bank", "unexpected_rate_cut", "confirmed", "mixed", 0.35, ["CATALYST", "RISK_OVERLAY"], "central_bank_rate"];
    }
    if (text.includes("disruption") && (text.includes("mine") || text.includes("uranium"))) {
      return ["commodity_supply", "producer_supply_disruption", "confirmed", "mixed", 0.3, ["CATALYST", "RISK_OVERLAY"], "commodity_supply"];
    }
    if (text.includes("investigation") || text.includes("safety probe")) {
      return ["regulatory_legal", "safety_investigation", "confirmed", "bearish", -0.72, ["RISK_OVERLAY", "VETO"], "regulatory"];
    }
    if (text.includes("approval") && (text.includes("restriction") || text.includes("restricted"))) {
      return ["regulatory_legal", "restricted_approval", "confirmed", "mixed", 0.22, ["CATALYST", "RISK_OVERLAY"], "regulatory"];
    }
    if (text.includes("profit warning") || text.includes("cuts outlook")) {
      return ["profit_warning", "company_specific_warning", "confirmed", "bearish", -0.86, ["CATALYST", "VETO", "EXIT_TRIGGER"], "profit_warning"];
    }
    if (text.includes("anticipated") && (text.includes("product") || text.includes("launch"))) {
      return ["product_technology", "anticipated_product_announcement", "confirmed", "neutral", 0.08, ["CONFIRMATION"], "product"];
    }
    if (text.includes("earnings") && (text.includes("cuts guidance") || text.includes("reduced guidance"))) {
      return ["earnings", "beat_but_guidance_reduced", "confirmed", "mixed", -0.28, ["RISK_OVERLAY", "CONFIRMATION"], "earnings"];
    }
    if (text.includes("earnings") && (text.includes("raises guidance") || text.includes("above expectations"))) {
      return ["earnings", "beat_and_raise", "confirmed", "bullish", 0.82, ["CATALYST", "CONFIRMATION"], "earnings"];
    }
    return ["unknown", "unknown", "confirmed", "neutral", 0, ["RISK_OVERLAY"], "unknown"];
  }

  function mockAnalyse(payload) {
    const items = Array.isArray(payload) ? payload : (payload.items || [payload]);
    const events = items.map((item, index) => makeEvent(item, index));
    const cluster = makeCluster(events);
    events.forEach((event) => {
      event.cluster_id = cluster.cluster_id;
    });
    const representative = events.find((event) => event.event_status === "denied")
      || events.find((event) => event.event_type === "merger_acquisition")
      || events[events.length - 1];
    const impacts = makeImpacts(representative);
    const signals = impacts.map((impact) => makeSignal(representative, cluster, impact));
    return {
      schema_version: "1.0.0",
      request_id: `mock_req_${Date.now()}`,
      stages: [
        {name: "Raw News", status: "COMPLETED", payload: items},
        {name: "Normalised News", status: "COMPLETED", payload: items},
        {name: "Event Classification", status: "COMPLETED", payload: events},
        {name: "Entity Resolution", status: "COMPLETED", payload: events.map((event) => event.entities)},
        {name: "Event Cluster", status: "COMPLETED", payload: [cluster]},
        {name: "Instrument Impacts", status: "COMPLETED", payload: impacts},
        {name: "News Signal", status: "COMPLETED", payload: signals}
      ],
      raw_items: items,
      normalised_items: items,
      events,
      clusters: [cluster],
      impacts,
      signals,
      errors: []
    };
  }

  function makeEvent(item, index) {
    const [eventType, subtype, status, direction, strength, roles, group] = classify(item);
    const symbol = item.known_ticker || detectSymbol(item.headline);
    const source = {
      source_name: item.source_name || "Unknown Source",
      source_type: item.source_type || "unknown",
      source_url: item.source_url || null,
      source_credibility: item.source_type === "blog" ? 0.45 : 0.86
    };
    const entities = symbol ? makeEntities(symbol) : macroEntities(eventType);
    return {
      schema_version: "1.0.0",
      event_id: `mock_evt_${index}_${slug(item.headline)}`,
      cluster_id: "",
      event_status: status,
      event_type: eventType,
      event_subtype: subtype,
      headline: item.headline,
      summary: item.body || item.headline,
      source,
      timestamps: {
        published_at: item.published_at || new Date().toISOString(),
        first_seen_at: item.published_at || new Date().toISOString(),
        processed_at: new Date().toISOString()
      },
      entities,
      analysis: {
        direction,
        directional_strength: strength,
        confidence: status === "unconfirmed" ? 0.32 : 0.82,
        quality: status === "unconfirmed" ? 0.44 : 0.86,
        surprise: 0.6,
        novelty: 0.7,
        expected_persistence: eventType === "rumour_unconfirmed" ? "intraday" : "multi_day"
      },
      strategy_roles: roles,
      lineage: {
        normaliser_version: "mock-normaliser",
        classifier_version: "mock-rules",
        entity_resolver_version: "mock-resolver",
        clusterer_version: "mock-clusterer",
        scorer_version: "mock-freshness",
        rule_id: subtype,
        event_group: group,
        raw_content_hash: `mock_hash_${slug(item.headline)}`,
        pipeline_version: "mock"
      },
      primary_symbol: symbol || (eventType === "central_bank" ? "JPM" : null),
      contradictions_detected: subtype.includes("denial") || subtype.includes("rejected")
    };
  }

  function makeEntities(symbol) {
    const rows = relations[symbol] || [[symbol, "instrument", "direct", "instrument", 1, 1]];
    return rows.map((row) => ({
      symbol: row[0],
      entity_type: row[1],
      relationship: row[2],
      scope: row[3],
      relevance: row[4],
      directional_multiplier: row[5],
      evidence: "mock fixture"
    }));
  }

  function macroEntities(eventType) {
    if (eventType !== "central_bank") {
      return [];
    }
    return [
      {symbol: "JPM", entity_type: "instrument", relationship: "sector_exposure", scope: "sector", relevance: 0.65, directional_multiplier: 1, evidence: "mock macro exposure"},
      {symbol: "XLF", entity_type: "etf", relationship: "sector_exposure", scope: "sector", relevance: 0.75, directional_multiplier: 1, evidence: "mock macro exposure"},
      {symbol: "QQQ", entity_type: "etf", relationship: "index_constituent", scope: "global_market", relevance: 0.65, directional_multiplier: 1, evidence: "mock macro exposure"},
      {symbol: "SPY", entity_type: "etf", relationship: "index_constituent", scope: "global_market", relevance: 0.52, directional_multiplier: 1, evidence: "mock macro exposure"}
    ];
  }

  function makeCluster(events) {
    const first = events[0];
    const duplicateCount = events.filter((event, index) => index > 0 && event.headline === first.headline).length;
    return {
      schema_version: "1.0.0",
      cluster_id: `mock_cluster_${slug(first.lineage.event_group)}_${first.primary_symbol || "macro"}`,
      canonical_event_id: first.event_id,
      event_type: first.event_type,
      event_group: first.lineage.event_group,
      headline_key: slug(first.headline),
      entity_symbols: Array.from(new Set(events.flatMap((event) => event.entities.map((entity) => entity.symbol).filter(Boolean)))),
      article_count: events.length,
      duplicate_count: duplicateCount,
      independent_source_count: new Set(events.map((event) => event.source.source_name)).size || 1,
      first_publication_at: first.timestamps.published_at,
      latest_material_update_at: events[events.length - 1].timestamps.published_at,
      event_ids: events.map((event) => event.event_id),
      source_names: Array.from(new Set(events.map((event) => event.source.source_name))),
      contradictions_detected: events.some((event) => event.contradictions_detected),
      items: events.map((event, index) => ({
        event_id: event.event_id,
        headline: event.headline,
        source_name: event.source.source_name,
        published_at: event.timestamps.published_at,
        duplicate: index > 0 && event.headline === first.headline,
        material_update: index > 0 && event.headline !== first.headline,
        confirmation_status: event.event_status,
        content_hash: event.lineage.raw_content_hash,
        canonical_event_id: first.event_id
      }))
    };
  }

  function makeImpacts(event) {
    if (event.event_subtype === "unexpected_rate_cut") {
      return [
        impact(event, "JPM", "instrument", "sector_exposure", "sector", "bearish", -0.24, 0.65),
        impact(event, "XLF", "etf", "sector_exposure", "sector", "mixed", -0.12, 0.75),
        impact(event, "QQQ", "etf", "index_constituent", "global_market", "bullish", 0.42, 0.65),
        impact(event, "SPY", "etf", "index_constituent", "global_market", "bullish", 0.22, 0.52)
      ];
    }
    if (event.event_subtype === "producer_supply_disruption") {
      return [
        impact(event, "CCJ", "instrument", "direct", "instrument", "bearish", -0.58, 1),
        impact(event, "URA", "etf", "commodity_exposure", "commodity", "bullish", 0.34, 0.55)
      ];
    }
    return event.entities.filter((entity) => entity.symbol).map((entity) => {
      const strength = event.analysis.directional_strength * entity.relevance * entity.directional_multiplier;
      return impact(event, entity.symbol, entity.entity_type, entity.relationship, entity.scope, direction(strength), strength, entity.relevance);
    });
  }

  function impact(event, symbol, entityType, relationship, scope, directionValue, strength, relevance) {
    return {
      schema_version: "1.0.0",
      impact_id: `mock_imp_${event.event_id}_${symbol}`,
      event_id: event.event_id,
      cluster_id: event.cluster_id,
      symbol,
      entity_type: entityType,
      relationship,
      scope,
      direction: directionValue,
      directional_strength: Number(strength.toFixed(4)),
      relevance,
      confidence: 0.76,
      quality: event.analysis.quality,
      reason: `${symbol} affected through ${relationship}.`,
      time_horizon: event.analysis.expected_persistence === "intraday" ? "INTRADAY" : "MULTI_DAY",
      expires_at: new Date(Date.now() + 86400000).toISOString()
    };
  }

  function makeSignal(event, cluster, impactRow) {
    const signalDirection = impactRow.direction === "mixed" ? "MIXED" : impactRow.directional_strength > 0.08 ? "LONG" : impactRow.directional_strength < -0.08 ? "SHORT" : "NEUTRAL";
    const veto = event.strategy_roles.includes("VETO");
    return {
      schema_version: "1.0.0",
      collector_type: "news_intelligence",
      signal_id: `mock_sig_${impactRow.symbol}`,
      event_id: event.event_id,
      cluster_id: cluster.cluster_id,
      instrument: {symbol: impactRow.symbol, exchange: null},
      signal: {
        direction: signalDirection,
        directional_strength: impactRow.directional_strength,
        confidence: impactRow.confidence,
        quality: impactRow.quality,
        freshness: 0.96,
        time_horizon: impactRow.time_horizon
      },
      roles: event.strategy_roles,
      evidence: {
        event_ids: cluster.event_ids,
        event_count: Math.max(1, cluster.article_count - cluster.duplicate_count),
        independent_source_count: cluster.independent_source_count,
        primary_source_present: ["company", "regulatory", "central_bank"].includes(event.source.source_type),
        article_count: cluster.article_count,
        duplicate_count: cluster.duplicate_count
      },
      decision: {
        can_trigger_trade: false,
        can_confirm_trade: event.strategy_roles.includes("CONFIRMATION") && !veto,
        can_veto_trade: veto,
        requires_technical_confirmation: true
      },
      generated_at: new Date().toISOString(),
      expiry_time: impactRow.expires_at,
      contradictions_detected: event.contradictions_detected || cluster.contradictions_detected
    };
  }

  function detectSymbol(headline) {
    const text = headline.toLowerCase();
    if (text.includes("nvidia")) return "NVDA";
    if (text.includes("apple")) return "AAPL";
    if (text.includes("exxon")) return "XOM";
    if (text.includes("moderna")) return "MRNA";
    if (text.includes("boeing")) return "BA";
    if (text.includes("cameco")) return "CCJ";
    return null;
  }

  function direction(strength) {
    if (strength > 0.08) return "bullish";
    if (strength < -0.08) return "bearish";
    return "neutral";
  }

  function slug(value) {
    return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40);
  }

  function mockSourceStatus() {
    return [
      {source_name: "Example Newswire", country_or_region: "US", source_class: "newswire", connector_type: "fixture", enabled: true, last_successful_ingestion: null, last_failure: null, items_ingested: 0, current_status: "OK"},
      {source_name: "Company Press Release", country_or_region: "US", source_class: "company", connector_type: "fixture", enabled: true, last_successful_ingestion: null, last_failure: null, items_ingested: 0, current_status: "OK"},
      {source_name: "Market Blog", country_or_region: "US", source_class: "blog", connector_type: "fixture", enabled: true, last_successful_ingestion: null, last_failure: null, items_ingested: 0, current_status: "DEGRADED"}
    ];
  }

  window.NewsFixtures = {
    list: baseFixtures,
    get(id) {
      return baseFixtures.find((fixture) => fixture.id === id) || baseFixtures[0];
    },
    itemsFor(id) {
      return fixtureItems(this.get(id));
    },
    mockAnalyse,
    mockSourceStatus
  };
})();
