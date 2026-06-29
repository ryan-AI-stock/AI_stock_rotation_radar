import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let chromium;
let playwrightRequest;
try {
  ({ chromium, request: playwrightRequest } = require("playwright"));
} catch {
  const playwright = await import("playwright");
  ({ chromium, request: playwrightRequest } = playwright);
}

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(SCRIPT_DIR, "..", "..");
const OUT = SCRIPT_DIR;
const PHASE6 = path.join(REPO, "outputs", "radar_tw50_0050_session_replay_phase6_201411_202312_20260629");
const RAW = path.join(OUT, "raw_sources");
fs.mkdirSync(RAW, { recursive: true });

const TARGETS = [
  { period: "2014Q4", target_date: "2014-12-31", year: "2014", month: "12", ndate: "20141231", yyyymm: "201412" },
  { period: "2016Q1", target_date: "2016-03-31", year: "2016", month: "03", ndate: "20160331", yyyymm: "201603" },
  { period: "2021Q4", target_date: "2021-12-31", year: "2021", month: "12", ndate: "20211231", yyyymm: "202112" },
  { period: "2023Q4", target_date: "2023-12-31", year: "2023", month: "12", ndate: "20231231", yyyymm: "202312" },
];

const YUANTA_PAGES = [
  "https://www.yuantaetfs.com/product/detail/0050/ratio",
  "https://www.yuantaetfs.com/tradeInfo/pcf/0050",
  "https://www.yuantaetfs.com/#/product/detail/0050/ratio",
  "https://www.yuantaetfs.com/#/tradeInfo/pcf/0050",
];

const BROWSER_EXECUTABLE_CANDIDATES = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
];

const FIELDS = {
  inventory: ["capture_id", "source", "page_url", "status", "http_status", "title", "request_count", "api_request_count", "relevant_response_count", "notes"],
  sitca: ["capture_id", "phase", "method", "url", "status", "http_status", "content_type", "request_headers", "post_body", "response_path", "response_sha256", "date_field_detected", "holdings_date", "row_count", "error"],
  yuanta: ["capture_id", "page_url", "method", "url", "status", "http_status", "content_type", "request_headers", "post_body", "response_path", "response_sha256", "date_field_detected", "holdings_date", "row_count", "api_family", "error"],
  replay: ["source", "period", "target_date", "template_url", "replay_url", "status", "http_status", "content_type", "response_path", "response_sha256", "date_field_detected", "holdings_date", "row_count", "accepted", "source_type", "formal_exact", "error", "notes"],
  raw: ["source", "period", "url", "retrieved_path", "content_type", "http_status", "sha256", "bytes", "notes"],
  sample: ["period", "source", "source_date", "holdings_date", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "parser_status", "notes"],
  accepted: ["period", "source", "source_date", "holdings_date", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "matched_evidence"],
  missing: ["period", "target_date", "sitca_capture_rows", "yuanta_capture_rows", "exact_replay_attempts", "parsed_sample_rows", "accepted_rows", "status", "blocker", "next_programmatic_source"],
  quality: ["source", "source_type", "formal_exact", "evidence_quality", "accepted_rows", "decision", "notes"],
  completed: ["step", "status", "completed_at", "notes"],
  failed: ["period", "step", "status", "error", "next_step"],
  runlog: ["started_at", "finished_at", "status", "sitca_requests", "yuanta_requests", "exact_replay_attempts", "parsed_rows", "accepted_rows", "notes"],
};

function now() {
  return new Date().toISOString();
}

function sha256(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function safeName(value) {
  return String(value).replace(/[^A-Za-z0-9_.-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 140) || "item";
}

function csvCell(value) {
  const text = value === undefined || value === null ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function writeCsv(file, rows, fields) {
  const lines = [fields.join(",")];
  for (const row of rows) {
    lines.push(fields.map((field) => csvCell(row[field])).join(","));
  }
  fs.writeFileSync(path.join(OUT, file), `${lines.join("\n")}\n`, "utf8");
}

function compactHeaders(headers) {
  const keep = {};
  for (const key of ["accept", "content-type", "origin", "referer", "user-agent", "x-requested-with"]) {
    if (headers[key]) keep[key] = headers[key];
  }
  if (headers.cookie) keep.cookie = "[masked]";
  return JSON.stringify(keep);
}

function detectDate(text) {
  const patterns = [
    ["anndate", /"anndate"\s*:\s*"([^"]+)"/i],
    ["DataDate", /"DataDate"\s*:\s*"([^"]+)"/i],
    ["date", /"(?:date|Date|navDate|searchDate)"\s*:\s*"([^"]+)"/i],
    ["chinese_label", /(資料日期|持股日期|年月)[^0-9]{0,12}([0-9]{3,4}[/-]?[0-9]{2}(?:[/-]?[0-9]{2})?)/],
  ];
  for (const [key, pattern] of patterns) {
    const match = text.match(pattern);
    if (match) return { field: key, date: normalizeDate(match[2] || match[1]) };
  }
  return { field: "", date: "" };
}

function normalizeDate(raw) {
  const text = String(raw || "").trim().replaceAll("/", "-");
  if (/^20\d{6}$/.test(text)) return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
  if (/^20\d{4}$/.test(text)) return `${text.slice(0, 4)}-${text.slice(4, 6)}`;
  if (/^\d{3}-?\d{2}-?\d{0,2}$/.test(text)) {
    const digits = text.replaceAll("-", "");
    const year = String(Number(digits.slice(0, 3)) + 1911).padStart(4, "0");
    if (digits.length >= 7) return `${year}-${digits.slice(3, 5)}-${digits.slice(5, 7)}`;
    return `${year}-${digits.slice(3, 5)}`;
  }
  return text;
}

function countTickerRows(text) {
  const matches = text.match(/(?:^|[^\d])(?:00[1-9]\d|0[1-9]\d{2}|[1-9]\d{3})(?:[^\d]|$)/g);
  return matches ? Math.min(matches.length, 500) : 0;
}

function parseHoldingsRows(text, limit = 80) {
  const rows = [];
  const seen = new Set();
  const objectMatches = text.match(/\{[^{}]{0,900}\}/g) || [];
  for (const objText of objectMatches) {
    const code = objText.match(/"(?:StockCode|stock_code|stk_cd|STK_CD|Code|code|股票代號)"\s*:\s*"?(?<ticker>\d{4})"?/i);
    if (!code) continue;
    const name = objText.match(/"(?:StockName|stock_name|stk_nm|STK_NM|Name|name|股票名稱)"\s*:\s*"(?<name>[^"]{1,40})"/i);
    const weight = objText.match(/"(?:Weight|weight|ratio|Ratio|proportion|Proportion|權重|持股比率)"\s*:\s*"?(?<weight>[0-9]+(?:\.[0-9]+)?)"?/i);
    const key = code.groups.ticker;
    if (!seen.has(key)) {
      rows.push({ ticker: key, name: name?.groups?.name || "", weight: weight?.groups?.weight || "" });
      seen.add(key);
    }
    if (rows.length >= limit) return rows;
  }
  return rows;
}

async function saveResponse(prefix, response) {
  try {
    const body = await response.body();
    const contentType = response.headers()["content-type"] || "";
    const ext = contentType.includes("json") ? "json" : contentType.includes("javascript") ? "js" : "html";
    const file = path.join(RAW, `${safeName(prefix)}.${ext}`);
    fs.writeFileSync(file, body);
    const text = body.toString("utf8");
    const date = detectDate(text);
    return {
      response_path: file,
      response_sha256: sha256(body),
      content_type: contentType,
      bytes: body.length,
      date_field_detected: date.field,
      holdings_date: date.date,
      row_count: countTickerRows(text),
      parsed_rows: parseHoldingsRows(text),
    };
  } catch (error) {
    return { response_path: "", response_sha256: "", content_type: "", bytes: 0, date_field_detected: "", holdings_date: "", row_count: 0, parsed_rows: [], error: `${error.name}: ${error.message}` };
  }
}

function isYuantaApi(url) {
  return /yuantaetfs\.com|etfapi\.yuantaetfs\.com|api\.yuantafunds\.com/i.test(url) && /(api\/bridge|api\/trans|ETFAPI|ETFBackstage|PCF|HoldStock|ratio|0050)/i.test(url);
}

async function captureSitca(browser, rawRows, samples) {
  const rows = [];
  const inventory = [];
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  page.on("response", async (response) => {
    const request = response.request();
    const url = response.url();
    if (!/sitca\.org\.tw/i.test(url)) return;
    const saved = await saveResponse(`sitca_${rows.length}_${request.method()}_${response.status()}`, response);
    rows.push({
      capture_id: "sitca_live_in2421",
      phase: "network",
      method: request.method(),
      url,
      status: response.ok() ? "http_ok" : "http_non_ok",
      http_status: response.status(),
      content_type: saved.content_type,
      request_headers: compactHeaders(request.headers()),
      post_body: request.postData() || "",
      response_path: saved.response_path,
      response_sha256: saved.response_sha256,
      date_field_detected: saved.date_field_detected,
      holdings_date: saved.holdings_date,
      row_count: saved.row_count,
      error: saved.error || "",
    });
    rawRows.push({ source: "sitca_live_capture", period: "live", url, retrieved_path: saved.response_path, content_type: saved.content_type, http_status: response.status(), sha256: saved.response_sha256, bytes: saved.bytes, notes: "browser network capture" });
  });

  let status = "started";
  let httpStatus = "";
  let title = "";
  let notes = "";
  try {
    const response = await page.goto("https://www.sitca.org.tw/ROC/Industry/IN2421.aspx", { waitUntil: "domcontentloaded", timeout: 25000 });
    httpStatus = response?.status() || "";
    title = await page.title().catch(() => "");
    for (const target of TARGETS) {
      await page.selectOption('select[name="ctl00$ContentPlaceHolder1$ddlQ_YEAR"]', target.year).catch(() => {});
      await page.waitForTimeout(500);
      await page.selectOption('select[name="ctl00$ContentPlaceHolder1$ddlQ_MONTH"]', target.month).catch(() => {});
      await page.waitForTimeout(500);
      const query = page.locator('input[name="ctl00$ContentPlaceHolder1$BtnQuery"]');
      if (await query.count()) {
        await Promise.race([
          page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {}),
          query.first().click({ timeout: 4000 }).catch(() => {}),
        ]);
      }
      await page.waitForTimeout(1500);
    }
    status = "captured";
  } catch (error) {
    status = "error";
    notes = `${error.name}: ${error.message}`;
  }
  inventory.push({
    capture_id: "sitca_live_in2421",
    source: "SITCA IN2421.aspx",
    page_url: "https://www.sitca.org.tw/ROC/Industry/IN2421.aspx",
    status,
    http_status: httpStatus,
    title,
    request_count: rows.length,
    api_request_count: rows.filter((row) => row.method === "POST").length,
    relevant_response_count: rows.filter((row) => Number(row.row_count) > 0).length,
    notes,
  });
  await context.close();
  return { rows, inventory, samples };
}

async function captureYuanta(browser, rawRows, samples) {
  const rows = [];
  const inventory = [];
  for (const pageUrl of YUANTA_PAGES) {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const page = await context.newPage();
    page.setDefaultTimeout(12000);
    const captureId = `yuanta_${safeName(pageUrl)}`;
    page.on("response", async (response) => {
      const request = response.request();
      const url = response.url();
      if (!isYuantaApi(url)) return;
      const saved = await saveResponse(`${captureId}_${rows.length}_${request.method()}_${response.status()}`, response);
      const apiFamily = /api\/bridge/i.test(url) ? "api_bridge" : /api\/trans/i.test(url) ? "api_trans" : /PCF/i.test(url) ? "pcf_related" : "other";
      rows.push({
        capture_id: captureId,
        page_url: pageUrl,
        method: request.method(),
        url,
        status: response.ok() ? "http_ok" : "http_non_ok",
        http_status: response.status(),
        content_type: saved.content_type,
        request_headers: compactHeaders(request.headers()),
        post_body: request.postData() || "",
        response_path: saved.response_path,
        response_sha256: saved.response_sha256,
        date_field_detected: saved.date_field_detected,
        holdings_date: saved.holdings_date,
        row_count: saved.row_count,
        api_family: apiFamily,
        error: saved.error || "",
      });
      rawRows.push({ source: "yuanta_live_capture", period: "live", url, retrieved_path: saved.response_path, content_type: saved.content_type, http_status: response.status(), sha256: saved.response_sha256, bytes: saved.bytes, notes: `browser network capture ${apiFamily}` });
      for (const parsed of saved.parsed_rows) {
        samples.push({ period: "live_current_or_page_date", source: url, source_date: "", holdings_date: saved.holdings_date, ticker: parsed.ticker, name: parsed.name, weight: parsed.weight, source_type: "endpoint_contract_sample", formal_exact: "false", evidence_quality: "date_mismatch_or_current_only", parser_status: "parsed_from_live_capture", notes: "not accepted unless holdings_date matches target period" });
      }
    });
    let status = "started";
    let httpStatus = "";
    let title = "";
    let notes = "";
    try {
      const response = await page.goto(pageUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
      httpStatus = response?.status() || "";
      await page.waitForLoadState("networkidle", { timeout: 12000 }).catch(() => {});
      title = await page.title().catch(() => "");
      status = "captured";
    } catch (error) {
      status = "error";
      notes = `${error.name}: ${error.message}`;
    }
    inventory.push({
      capture_id: captureId,
      source: "Yuanta 0050 live page",
      page_url: pageUrl,
      status,
      http_status: httpStatus,
      title,
      request_count: rows.filter((row) => row.capture_id === captureId).length,
      api_request_count: rows.filter((row) => row.capture_id === captureId && /api_/i.test(row.api_family)).length,
      relevant_response_count: rows.filter((row) => row.capture_id === captureId && Number(row.row_count) > 0).length,
      notes,
    });
    await context.close();
  }
  return { rows, inventory, samples };
}

function buildReplayUrls(yuantaRows) {
  const templates = new Set();
  for (const row of yuantaRows) {
    if (/api\/bridge|api\/trans/i.test(row.url)) templates.add(row.url);
  }
  templates.add("https://www.yuantaetfs.com/api/bridge?APIType=ETFAPI&CompanyName=YUANTAFUNDS&PageName=%2FtradeInfo%2Fpcf%2F0050&DeviceId=null&FuncId=PCF%2FDaily&ticker=0050&ndate=__NDATE__");
  templates.add("https://www.yuantaetfs.com/api/trans?APIType=ETFBackstage&CompanyName=YUANTAFUNDS&PageName=%2FtradeInfo%2Fpcf%2F0050&DeviceId=null&FuncId=ETFPCF&stk_cd=0050");
  templates.add("https://www.yuantaetfs.com/api/bridge?APIType=ETFAPI&CompanyName=YUANTAFUNDS&PageName=%2Fproduct%2Fdetail%2F0050%2Fratio&DeviceId=null&FuncId=PCF%2FDaily&ticker=0050&ndate=__NDATE__");
  return [...templates].slice(0, 8);
}

function withTargetDate(template, target) {
  let url = template.replace(/__NDATE__/g, target.ndate);
  try {
    const parsed = new URL(url);
    for (const key of ["ndate", "date", "DataDate", "anndate"]) {
      if (parsed.searchParams.has(key)) parsed.searchParams.set(key, key === "ndate" ? target.ndate : target.target_date);
    }
    if (!parsed.searchParams.has("ndate") && /PCF\/Daily|PCF%2FDaily/i.test(url)) parsed.searchParams.set("ndate", target.ndate);
    if (!parsed.searchParams.has("ticker") && /PCF\/Daily|PCF%2FDaily/i.test(url)) parsed.searchParams.set("ticker", "0050");
    return parsed.toString();
  } catch {
    return url;
  }
}

async function runReplay(yuantaRows, rawRows, samples, accepted) {
  const rows = [];
  const api = await playwrightRequest.newContext({ ignoreHTTPSErrors: true, extraHTTPHeaders: { "user-agent": "Mozilla/5.0 RadarDataPhase7/1.0", accept: "application/json,text/html,*/*" } });
  const templates = buildReplayUrls(yuantaRows);
  for (const target of TARGETS) {
    for (const template of templates) {
      const replayUrl = withTargetDate(template, target);
      let record = { source: "yuanta_exact_replay", period: target.period, target_date: target.target_date, template_url: template, replay_url: replayUrl, status: "", http_status: "", content_type: "", response_path: "", response_sha256: "", date_field_detected: "", holdings_date: "", row_count: 0, accepted: "false", source_type: "browser_capture_exact_replay", formal_exact: "false", error: "", notes: "" };
      try {
        const response = await api.get(replayUrl, { timeout: 15000 });
        const body = await response.body();
        const contentType = response.headers()["content-type"] || "";
        const ext = contentType.includes("json") ? "json" : "html";
        const file = path.join(RAW, `${safeName(target.period)}_replay_${rows.length}.${ext}`);
        fs.writeFileSync(file, body);
        const text = body.toString("utf8");
        const date = detectDate(text);
        const parsedRows = parseHoldingsRows(text);
        record = { ...record, status: response.ok() ? "http_ok" : "http_non_ok", http_status: response.status(), content_type: contentType, response_path: file, response_sha256: sha256(body), date_field_detected: date.field, holdings_date: date.date, row_count: parsedRows.length || countTickerRows(text), notes: "accepted only if holdings/source date matches target period" };
        rawRows.push({ source: "yuanta_exact_replay", period: target.period, url: replayUrl, retrieved_path: file, content_type: contentType, http_status: response.status(), sha256: record.response_sha256, bytes: body.length, notes: "exact replay from browser-captured/common params" });
        const targetMatches = date.date && (date.date === target.target_date || date.date === target.target_date.slice(0, 7));
        for (const parsed of parsedRows) {
          const sample = { period: target.period, source: replayUrl, source_date: date.date, holdings_date: date.date, ticker: parsed.ticker, name: parsed.name, weight: parsed.weight, source_type: "browser_capture_exact_replay", formal_exact: "false", evidence_quality: targetMatches ? "target_date_matched_manual_candidate" : "date_mismatch_or_missing_date", parser_status: "parsed_from_replay_response", notes: "not accepted unless date matches target period" };
          samples.push(sample);
          if (targetMatches) {
            accepted.push({ period: target.period, source: replayUrl, source_date: date.date, holdings_date: date.date, ticker: parsed.ticker, name: parsed.name, weight: parsed.weight, source_type: "source_backed_manual_proxy", formal_exact: "false", evidence_quality: "target_date_matched_browser_replay", matched_evidence: `${file}#${parsed.ticker}` });
          }
        }
        if (targetMatches && parsedRows.length > 0) record.accepted = "true";
      } catch (error) {
        record = { ...record, status: "error", error: `${error.name}: ${error.message}` };
      }
      rows.push(record);
    }
  }
  await api.dispose();
  return rows;
}

function makeSummary(inventory, sitcaRows, yuantaRows, replayRows, samples, accepted, missing) {
  const sitcaPosts = sitcaRows.filter((row) => row.method === "POST");
  const yuantaApis = yuantaRows.filter((row) => /api_bridge|api_trans/i.test(row.api_family));
  const lines = [
    "# 0050 historical constituents Phase 7: browser network capture",
    "",
    "## Conclusion",
    "",
    "Phase 7 completed browser-based network capture and exact replay attempts for SITCA and Yuanta 0050 pages.",
    "",
    `Accepted historical rows: ${accepted.length}`,
    `Parsed holding sample rows: ${samples.length}`,
    `SITCA captured requests: ${sitcaRows.length}`,
    `SITCA captured POST requests: ${sitcaPosts.length}`,
    `Yuanta captured relevant requests: ${yuantaRows.length}`,
    `Yuanta captured api bridge/trans requests: ${yuantaApis.length}`,
    `Exact replay attempts: ${replayRows.length}`,
    "",
    accepted.length
      ? "At least one target-period row was accepted because the response date matched the target period."
      : "No target-period 0050 holdings list was accepted. Current/near-current/date-mismatched payloads were kept only as endpoint contract samples.",
    "",
    "## SITCA finding",
    "",
    sitcaPosts.length
      ? `The live browser capture saw ${sitcaPosts.length} SITCA POST request(s). Review sitca_network_requests.csv for exact masked headers and post body.`
      : "The live browser run loaded IN2421.aspx but did not observe a successful POST returning holdings rows. This indicates either the page query flow is blocked/headless-sensitive or the available form does not expose the target table without an additional browser event/control path.",
    "",
    "## Yuanta finding",
    "",
    yuantaApis.length
      ? "The live browser capture observed Yuanta API bridge/trans requests and saved their response samples. Exact replay was attempted against the four target periods."
      : "The live browser capture did not expose a usable historical Yuanta API request with target-date support. Static endpoint names alone remain insufficient.",
    "",
    "## Period status",
    "",
    "| period | target_date | replay_attempts | parsed_sample_rows | accepted_rows | status |",
    "|---|---:|---:|---:|---:|---|",
    ...missing.map((row) => `| ${row.period} | ${row.target_date} | ${row.exact_replay_attempts} | ${row.parsed_sample_rows} | ${row.accepted_rows} | ${row.status} |`),
    "",
    "## Next programmatic route",
    "",
    "1. Use non-headless Chrome with persisted profile only for network capture, still masking cookies, to check whether SITCA rejects headless Chromium or requires a UI-only event path.",
    "2. Query SITCA site search/static file directories for IN2421 downloadable monthly artifacts or alternate endpoints behind the ASP.NET page.",
    "3. Trace Yuanta Nuxt store getters for getBaseUrl/getCommonParameters and replay through the same origin with captured DeviceId/common params; if live API only returns current PCF, keep it as endpoint contract sample, not historical evidence.",
    "4. Continue treating TWSE/Taiwan Index constituents as proxy-only unless a source decision ties them to ETF holdings.",
    "",
    "## Guardrails",
    "",
    "- formal_exact=false",
    "- current_snapshot_used_as_historical=false",
    "- formal_model_changed=false",
    "- trade_decision_changed=false",
    "- raw browser responses are retained under raw_sources/ and excluded from git",
  ];
  fs.writeFileSync(path.join(OUT, "final_summary_zh.md"), `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const started = now();
  fs.writeFileSync(path.join(OUT, "current_step.txt"), "running browser capture\n", "utf8");
  const rawRows = [];
  const samples = [];
  const accepted = [];
  const executablePath = BROWSER_EXECUTABLE_CANDIDATES.find((candidate) => fs.existsSync(candidate));
  const browser = await chromium.launch({
    headless: true,
    executablePath,
    args: ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
  });
  const sitca = await captureSitca(browser, rawRows, samples);
  const yuanta = await captureYuanta(browser, rawRows, samples);
  await browser.close();
  const replayRows = await runReplay(yuanta.rows, rawRows, samples, accepted);
  const missing = TARGETS.map((target) => {
    const replayCount = replayRows.filter((row) => row.period === target.period).length;
    const sampleCount = samples.filter((row) => row.period === target.period).length;
    const acceptedCount = accepted.filter((row) => row.period === target.period).length;
    return {
      period: target.period,
      target_date: target.target_date,
      sitca_capture_rows: sitca.rows.length,
      yuanta_capture_rows: yuanta.rows.length,
      exact_replay_attempts: replayCount,
      parsed_sample_rows: sampleCount,
      accepted_rows: acceptedCount,
      status: acceptedCount ? "accepted_manual_proxy_rows" : "missing_accepted_rows",
      blocker: acceptedCount ? "" : "Live browser capture/replay did not return target-date 0050 holdings rows.",
      next_programmatic_source: "Non-headless Chrome/devtools capture with persisted profile, then SITCA static endpoint discovery or Yuanta same-origin replay with full common params.",
    };
  });
  const quality = [
    { source: "SITCA IN2421.aspx browser capture", source_type: "browser_capture_candidate", formal_exact: "false", evidence_quality: sitca.rows.some((row) => Number(row.row_count) > 0) ? "rows_detected_needs_date_match" : "no_holdings_rows_detected", accepted_rows: 0, decision: "not_formal_ready", notes: "accepted only if target date rows are parsed" },
    { source: "Yuanta 0050 browser capture", source_type: "endpoint_contract_sample", formal_exact: "false", evidence_quality: yuanta.rows.length ? "live_api_contract_captured" : "no_api_contract_captured", accepted_rows: accepted.length, decision: accepted.length ? "manual_proxy_partial" : "not_formal_ready", notes: "current/date-mismatched payloads are not historical evidence" },
    { source: "Phase7 exact replay", source_type: "browser_capture_exact_replay", formal_exact: "false", evidence_quality: accepted.length ? "target_date_rows_found" : "no_target_date_rows", accepted_rows: accepted.length, decision: accepted.length ? "manual_proxy_partial" : "blocked_partial", notes: "no current snapshot backfill" },
  ];
  const completed = [{ step: "phase7_browser_network_capture", status: "completed_partial", completed_at: now(), notes: `accepted_historical_rows=${accepted.length}` }];
  const failed = missing.filter((row) => row.accepted_rows === 0).map((row) => ({ period: row.period, step: "target_period_acceptance", status: "missing_accepted_rows", error: row.blocker, next_step: row.next_programmatic_source }));
  const runlog = [{ started_at: started, finished_at: now(), status: accepted.length ? "completed_partial_with_rows" : "completed_partial_no_valid_dated_rows", sitca_requests: sitca.rows.length, yuanta_requests: yuanta.rows.length, exact_replay_attempts: replayRows.length, parsed_rows: samples.length, accepted_rows: accepted.length, notes: `read_phase6=${PHASE6}` }];
  const inventory = [...sitca.inventory, ...yuanta.inventory];

  writeCsv("browser_capture_inventory.csv", inventory, FIELDS.inventory);
  writeCsv("sitca_network_requests.csv", sitca.rows, FIELDS.sitca);
  writeCsv("yuanta_network_requests.csv", yuanta.rows, FIELDS.yuanta);
  writeCsv("exact_replay_attempts.csv", replayRows, FIELDS.replay);
  writeCsv("raw_source_archive_manifest.csv", rawRows, FIELDS.raw);
  writeCsv("parsed_holdings_sample.csv", samples, FIELDS.sample);
  writeCsv("accepted_historical_rows.csv", accepted, FIELDS.accepted);
  writeCsv("missing_periods.csv", missing, FIELDS.missing);
  writeCsv("source_quality_decision.csv", quality, FIELDS.quality);
  writeCsv("completed.csv", completed, FIELDS.completed);
  writeCsv("failed.csv", failed, FIELDS.failed);
  writeCsv("run_log.csv", runlog, FIELDS.runlog);
  fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify({
    task_id: "TASK-RADAR-DATA-TW50-0050-BROWSER-NETWORK-CAPTURE-PHASE7-20260629",
    output_dir: OUT,
    previous_output: PHASE6,
    generated_at: now(),
    target_periods: TARGETS,
    accepted_historical_rows: accepted.length,
    parsed_holdings_sample_rows: samples.length,
    sitca_network_request_count: sitca.rows.length,
    yuanta_network_request_count: yuanta.rows.length,
    exact_replay_attempt_count: replayRows.length,
    formal_exact: false,
    formal_model_changed: false,
    current_snapshot_used_as_historical: false,
  }, null, 2), "utf8");
  makeSummary(inventory, sitca.rows, yuanta.rows, replayRows, samples, accepted, missing);
  fs.writeFileSync(path.join(OUT, "current_step.txt"), "completed_partial\n", "utf8");
}

main().catch((error) => {
  fs.writeFileSync(path.join(OUT, "current_step.txt"), `failed: ${error.name}: ${error.message}\n`, "utf8");
  throw error;
});
