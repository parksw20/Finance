/* 재무 대시보드 프론트엔드 */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const state = { year: null, period: 'FY', meta: null, sectors: null, screener: null, company: null, peers: [], charts: {}, sort: { key: 'revenue', dir: -1 }, filters: { sectors: new Set() } };
/** 기간 라벨: 연간 '2025년', 분기 '2025 Q2' */
const L = (yy) => state.period === 'FY' ? `${yy}년` : `${yy} ${state.period}`;
const GL = () => state.period === 'FY' ? '성장률' : '성장률(YoY)';
const PREV = () => state.period === 'FY' ? '전년' : '전년 동기';
const SGA = ['① 인건비', '② 복리후생비', '③ 지급/용역수수료', '④ 광고선전비', '⑤ 임차/관리비', '⑥ 감가상각비', '⑦ 물류/운반비', '⑧ 연구개발비', '⑨ 기타판관비'];
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const SERIES = () => ['--s1', '--s2', '--s3', '--s4', '--s5', '--s6', '--s7', '--s8'].map(css);

/* ---------- 포맷 ---------- */
const fmtN = (v, d = 0) => (v == null || isNaN(v)) ? '<span class="muted">–</span>' : v.toLocaleString('ko-KR', { maximumFractionDigits: d, minimumFractionDigits: d });
const fmtP = (v, d = 1, sign = false) => {
  if (v == null || isNaN(v) || !isFinite(v)) return '<span class="muted">–</span>';
  const s = (v * 100).toFixed(d) + '%';
  const cls = sign ? (v > 0 ? 'pos' : v < 0 ? 'neg' : '') : '';
  return `<span class="${cls}">${sign && v > 0 ? '+' : ''}${s}</span>`;
};
const fmtPp = (v) => (v == null || isNaN(v)) ? '<span class="muted">–</span>' : `<span class="${v > 0 ? 'pos' : v < 0 ? 'neg' : ''}">${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%p</span>`;
const badge = (v) => `<span class="badge ${v === '-' || !v ? 'dash' : v}">${v || '-'}</span>`;
const ratings = (m) => `<div class="rating-row"><span class="lbl">성장성</span>${badge(m.rating_growth)}<span class="lbl">수익성</span>${badge(m.rating_profit)}<span class="lbl">안정성</span>${badge(m.rating_stability)}</div>`;
const listedChip = (m) => m.listed == null ? '' : ` <span class="chip sm ${m.listed ? 'listed' : 'unlisted'}" title="${m.listed ? (m.stock_code ? '종목코드 ' + m.stock_code : '상장사') : '비상장사 (DART 재무제표 API 미제공)'}">${m.listed ? '상장' : '비상장'}</span>`;
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ---------- API ---------- */
const qp = () => `year=${state.year}&period=${state.period}`;
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

/* ---------- 차트 공통 ---------- */
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.font.size = 11;
function chart(id, cfg) {
  if (state.charts[id]) state.charts[id].destroy();
  const ctx = $('#' + id).getContext('2d');
  const text2 = css('--text-2'), border = css('--border');
  Chart.defaults.color = text2;
  cfg.options = cfg.options || {};
  cfg.options.maintainAspectRatio = false;
  cfg.options.plugins = { legend: { display: false }, tooltip: { backgroundColor: css('--surface'), titleColor: css('--text'), bodyColor: text2, borderColor: border, borderWidth: 1 }, ...(cfg.options.plugins || {}) };
  for (const ax of Object.values(cfg.options.scales || {})) { ax.grid = { color: border, ...(ax.grid || {}) }; ax.ticks = { color: text2, ...(ax.ticks || {}) }; ax.border = { color: border }; }
  state.charts[id] = new Chart(ctx, cfg);
}
const pctTick = (v) => (v * 100).toFixed(0) + '%';
const barStyle = { borderRadius: 4, borderSkipped: 'start', maxBarThickness: 26 };

/* ---------- 초기화 ---------- */
async function init() {
  $('#theme-btn').onclick = () => {
    const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.dataset.theme = cur === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('theme', document.documentElement.dataset.theme); } catch (e) {}
    rerenderAll();
  };
  try { const t = localStorage.getItem('theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
  $$('#tabs button').forEach((b) => b.onclick = () => showView(b.dataset.view));
  $('#year-select').onchange = (e) => { const [y, p] = e.target.value.split('|'); state.year = +y; state.period = p; loadAll(); };
  await loadMeta();
  await loadAll();
  bindScreener();
  bindCompany();
  bindData();
  const hash = location.hash.replace('#', '');
  if (hash) showView(hash.split('/')[0]);
  setInterval(loadMeta, 30000);
}

function showView(v) {
  $$('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.view === v));
  $$('section.view').forEach((s) => s.classList.toggle('active', s.id === 'view-' + v));
  location.hash = v;
  if (v === 'data') loadData();
}

async function loadMeta() {
  const m = await api('/api/meta');
  state.meta = m;
  if (!state.year) state.year = m.default_year;
  const sel = $('#year-select');
  const order = { FY: 0, Q1: 1, Q2: 2, Q3: 3, Q4: 4 };
  const opts = m.periods.filter((x) => x.period === 'FY' ? x.companies >= 1 : x.companies >= 1).sort((a, b) => (b.year - a.year) || (order[a.period] - order[b.period]));
  sel.innerHTML = opts.map((x) => `<option value="${x.year}|${x.period}" ${x.year === state.year && x.period === state.period ? 'selected' : ''}>${x.period === 'FY' ? `${x.year}년 연간` : `${x.year}년 ${x.period.replace('Q', '')}분기`} (${x.companies}개사)</option>`).join('');
  $('#unit-note').textContent = state.period === 'FY' ? '단위: 억원' : `단위: 억원 · ${state.period.replace('Q', '')}분기 기준, 성장률은 전년 동기 대비`;
  const lr = m.last_refresh;
  const dot = m.refresh_running ? 'running' : lr ? (lr.status === 'ok' ? 'ok' : lr.status === 'error' ? 'error' : '') : '';
  $('#refresh-info').innerHTML = `<span class="status-dot ${dot}"></span>${m.refresh_running ? '갱신 중…' : lr ? `최근 갱신 ${lr.finished_at || lr.started_at} (${lr.source})` : '갱신 이력 없음'}${m.next_run ? ` · 다음 ${m.next_run.slice(0, 16).replace('T', ' ')}` : ''}`;
}

async function loadAll() {
  const [s, sc] = await Promise.all([api(`/api/sectors?${qp()}`), api(`/api/screener?${qp()}`)]);
  state.sectors = s; state.screener = sc;
  renderSector(); renderScreener();
  if (state.company) loadCompany(state.company.id);
}
function rerenderAll() { if (state.sectors) renderSector(); if (state.companyData) renderCompany(state.companyData); }

/* ================= 업종 ================= */
function renderSector() {
  const { sectors, total, rankings, year } = state.sectors;
  const py = year - 1;
  $('#sector-kpi').innerHTML = [
    ['전체 매출', fmtN(total?.revenue), `${L(py)} ${fmtN(total?.revenue_prev)} · ${fmtP(total?.revenue_growth, 1, true)}`],
    ['전체 영업이익', fmtN(total?.op), `영업이익률 ${fmtP(total?.opm)} (${L(py)} ${fmtP(total?.opm_prev)})`],
    ['매출원가율 / 판관비율', `${fmtP(total?.cogs_ratio)} / ${fmtP(total?.sga_ratio)}`, `${L(py)} ${fmtP(total?.cogs_ratio_prev)} / ${fmtP(total?.sga_ratio_prev)}`],
    ['부채비율', fmtP(total?.debt_ratio, 0), `리스부채 제외 · ${L(py)} ${fmtP(total?.debt_ratio_prev, 0)}`],
    ['집계 기업 수', `${total?.company_count ?? 0}<span class="muted" style="font-size:14px">개사</span>`, `${sectors.length}개 업종 · 등록 ${state.meta.company_count}개사 (상장 ${state.meta.listed_count})`],
  ].map(([t, v, s]) => `<div class="card tile"><h3>${t}</h3><div class="value">${v}</div><div class="sub">${s}</div></div>`).join('');

  const labels = sectors.map((s) => s.sector);
  const colorFor = (v) => (v >= 0 ? css('--s1') : css('--s8'));
  chart('ch-sector-growth', { type: 'bar', data: { labels, datasets: [{ data: sectors.map((s) => s.revenue_growth), backgroundColor: sectors.map((s) => colorFor(s.revenue_growth)), ...barStyle }] },
    options: { indexAxis: 'y', scales: { x: { ticks: { callback: pctTick } }, y: { grid: { display: false } } }, plugins: { tooltip: { callbacks: { label: (c) => ` ${(c.raw * 100).toFixed(1)}%  (${fmtN(sectors[c.dataIndex].revenue_prev)} → ${fmtN(sectors[c.dataIndex].revenue)}억)`.replace(/<[^>]+>/g, '') } } } } });
  chart('ch-sector-opm', { type: 'bar', data: { labels, datasets: [{ label: L(py), data: sectors.map((s) => s.opm_prev), backgroundColor: css('--border'), ...barStyle }, { label: L(year), data: sectors.map((s) => s.opm), backgroundColor: sectors.map((s) => colorFor(s.opm)), ...barStyle }] },
    options: { indexAxis: 'y', scales: { x: { ticks: { callback: pctTick } }, y: { grid: { display: false } } }, plugins: { legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label} ${(c.raw * 100).toFixed(1)}%` } } } } });

  $('#tbl-sector').innerHTML = `<thead><tr>
    <th>#</th><th class="l">업종</th><th class="l">간략 평가</th>
    <th class="group-start">매출 ${L(py)}</th><th>매출 ${L(year)}</th><th>${GL()}</th>
    <th class="group-start">영업이익 ${L(py)}</th><th>영업이익 ${L(year)}</th><th>증감액</th><th>영업이익률</th>
    <th class="group-start">매출원가율</th><th>판관비율</th><th>부채비율</th><th>재고보유일수</th><th>기업수</th></tr></thead><tbody>` +
    (total ? `<tr class="total"><td></td><td class="l">${total.name}</td><td class="l">${ratings(total)}</td><td class="group-start">${fmtN(total.revenue_prev)}</td><td>${fmtN(total.revenue)}</td><td>${fmtP(total.revenue_growth, 1, true)}</td><td class="group-start">${fmtN(total.op_prev)}</td><td>${fmtN(total.op)}</td><td>${fmtN(total.op_change)}</td><td>${fmtP(total.opm)}</td><td class="group-start">${fmtP(total.cogs_ratio)}</td><td>${fmtP(total.sga_ratio)}</td><td>${fmtP(total.debt_ratio, 0)}</td><td>${fmtN(total.inventory_days)}</td><td>${total.company_count}</td></tr>` : '') +
    sectors.map((s, i) => `<tr class="clickable" data-sector="${esc(s.sector)}"><td>${i + 1}</td><td class="l name">${esc(s.sector)}</td><td class="l">${ratings(s)}</td><td class="group-start">${fmtN(s.revenue_prev)}</td><td>${fmtN(s.revenue)}</td><td>${fmtP(s.revenue_growth, 1, true)}</td><td class="group-start">${fmtN(s.op_prev)}</td><td>${fmtN(s.op)}</td><td>${fmtN(s.op_change)}</td><td>${fmtP(s.opm)}</td><td class="group-start">${fmtP(s.cogs_ratio)}</td><td>${fmtP(s.sga_ratio)}</td><td>${fmtP(s.debt_ratio, 0)}</td><td>${fmtN(s.inventory_days)}</td><td>${s.company_count}</td></tr>`).join('') + '</tbody>';
  $$('#tbl-sector tr.clickable').forEach((tr) => tr.onclick = () => { state.filters.sectors = new Set([tr.dataset.sector]); renderScreener(); showView('screener'); });

  const sgaKeys = ['① 인건비', '④ 광고선전비', '③ 지급/용역수수료', '⑦ 물류/운반비', '⑥ 감가상각비', '⑤ 임차/관리비', '② 복리후생비', '⑨ 기타판관비'];
  const cols = SERIES();
  chart('ch-sector-sga', { type: 'bar', data: { labels, datasets: sgaKeys.map((k, i) => ({ label: k.replace(/^.\s?/, ''), data: sectors.map((s) => s.sga_items[k]?.ratio || 0), backgroundColor: cols[i % cols.length], borderWidth: 1, borderColor: css('--surface'), maxBarThickness: 30 })) },
    options: { indexAxis: 'y', scales: { x: { stacked: true, ticks: { callback: pctTick } }, y: { stacked: true, grid: { display: false } } }, plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label} ${(c.raw * 100).toFixed(1)}%` } } } } });
  chart('ch-sector-debt', { type: 'bar', data: { labels, datasets: [{ label: L(py), data: sectors.map((s) => s.debt_ratio_prev), backgroundColor: css('--border'), ...barStyle }, { label: L(year), data: sectors.map((s) => s.debt_ratio), backgroundColor: sectors.map((s) => (s.debt_ratio > 2 ? css('--s8') : s.debt_ratio < 1 ? css('--s1') : css('--neutral'))), ...barStyle }] },
    options: { indexAxis: 'y', scales: { x: { ticks: { callback: pctTick } }, y: { grid: { display: false } } }, plugins: { legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label} ${(c.raw * 100).toFixed(0)}%` } } } } });

  const rankCard = (title, list, fmt = (v) => fmtP(v, 1, true)) => {
    const max = Math.max(...list.map((r) => Math.abs(r.value || 0)), 1e-9);
    return `<div class="card"><h3>${title}</h3><ol class="rank-list">${list.map((r, i) => `<li><span class="idx">${i + 1}</span><span class="nm" data-id="${r.id ?? ''}">${esc(r.name)}${r.sector ? ` <span class="sec">${esc(r.sector)}</span>` : ''}</span><span class="bar" style="width:${Math.abs(r.value) / max * 60}px;background:${r.value < 0 ? css('--s8') : css('--s1')}"></span><span class="val">${fmt(r.value)}</span></li>`).join('') || '<li class="muted">해당 없음</li>'}</ol></div>`;
  };
  $('#rankings').innerHTML = rankCard(`매출 ${GL()} 상위 <small>매출 100억 이상</small>`, rankings.growth) + rankCard('역성장 기업', rankings.decline) + rankCard('영업이익률 상위', rankings.opm, (v) => fmtP(v)) + rankCard('매출원가율 낮은 기업', rankings.cogs_ratio, (v) => fmtP(v)) + rankCard('광고선전비 비율 높은 기업', rankings.ad_ratio, (v) => fmtP(v)) + rankCard('업종 성장률 / 영업이익률', rankings.sector_growth.map((r) => ({ ...r, name: r.name, sector: `영업이익률 ${((rankings.sector_opm.find((x) => x.name === r.name)?.value || 0) * 100).toFixed(1)}%` })));
  $$('#rankings .nm[data-id]').forEach((el) => { if (el.dataset.id) el.onclick = () => openCompany(+el.dataset.id); });
}

/* ================= 스크리너 ================= */
const COLSETS = {
  pl: (y) => [
    { g: '매출', cols: [[L(y - 1), 'revenue_prev', fmtN], [L(y), 'revenue', fmtN], [GL(), 'revenue_growth', (v) => fmtP(v, 1, true)]] },
    { g: '매출원가율', cols: [[L(y), 'cogs_ratio', fmtP], ['증감', 'cogs_ratio_delta', fmtPp]] },
    { g: '판관비율', cols: [[L(y), 'sga_ratio', fmtP], ['증감', 'sga_ratio_delta', fmtPp]] },
    { g: '영업이익', cols: [[L(y - 1), 'op_prev', fmtN], [L(y), 'op', fmtN], ['이익률', 'opm', fmtP], ['증감', 'opm_delta', fmtPp]] },
    { g: '순이익', cols: [['순이익률', 'net_margin', fmtP]] },
  ],
  amt: (y) => [
    { g: '매출', cols: [[L(y - 1), 'revenue_prev', fmtN], [L(y), 'revenue', fmtN]] },
    { g: '매출원가', cols: [[L(y - 1), 'cogs_prev', fmtN], [L(y), 'cogs', fmtN]] },
    { g: '매출총이익', cols: [[L(y - 1), 'gross_prev', fmtN], [L(y), 'gross', fmtN]] },
    { g: '판관비', cols: [[L(y - 1), 'sga_prev', fmtN], [L(y), 'sga', fmtN]] },
    { g: '영업이익', cols: [[L(y - 1), 'op_prev', fmtN], [L(y), 'op', fmtN], ['증감액', 'op_change', fmtN]] },
    { g: '당기순이익', cols: [[L(y - 1), 'net_prev', fmtN], [L(y), 'net', fmtN]] },
  ],
  sga: (y) => [{ g: `판관비 항목별 매출 대비 비율 (${L(y)})`, cols: SGA.map((k) => [k.replace(/^.\s?/, ''), 'sga_' + k, fmtP]) }, { g: '합계', cols: [['판관비율', 'sga_ratio', fmtP], ['총비용률', 'total_cost_ratio', fmtP]] }],
  bs: (y) => [
    { g: `재무상태 (${L(y)})`, cols: [['자산총계', 'assets', fmtN], ['부채총계', 'liabilities', fmtN], ['자본총계', 'equity', fmtN], ['부채비율', 'debt_ratio', (v) => fmtP(v, 0)], ['리스부채', 'lease_liab', fmtN], ['사용권자산', 'rou_asset', fmtN]] },
    { g: '재고', cols: [['재고자산', 'inventory', fmtN], ['회전율', 'inventory_turnover', (v) => fmtN(v, 1)], ['보유일수', 'inventory_days', fmtN]] },
  ],
  cash: (y) => [
    { g: `운전자본 (${L(y)})`, cols: [['순운전자본+', 'nwc_plus', fmtN], ['순운전자본−', 'nwc_minus', fmtN], ['순가용현금', 'net_cash', fmtN], [`${PREV()} 순가용현금`, 'net_cash_prev', fmtN]] },
    { g: '현금흐름', cols: [['영업', 'cf_op', fmtN], ['투자', 'cf_inv', fmtN], ['재무', 'cf_fin', fmtN], ['현금 증감', 'cf_net', fmtN]] },
  ],
};
const ratingsCompact = (m) => `<span class="rating-compact">${badge(m.rating_growth)}${badge(m.rating_profit)}${badge(m.rating_stability)}</span>`;
function enrich(r) {
  r.cogs_ratio_delta = r.cogs_ratio != null && r.cogs_ratio_prev != null ? r.cogs_ratio - r.cogs_ratio_prev : null;
  r.sga_ratio_delta = r.sga_ratio != null && r.sga_ratio_prev != null ? r.sga_ratio - r.sga_ratio_prev : null;
  r.opm_delta = r.opm != null && r.opm_prev != null ? r.opm - r.opm_prev : null;
  SGA.forEach((k) => r['sga_' + k] = r.sga_items?.[k]?.ratio ?? null);
  r.total_cost_ratio = r.cogs_ratio != null && r.sga_ratio != null ? r.cogs_ratio + r.sga_ratio : null;
  return r;
}
function bindScreener() {
  const sizes = ['①0~10억', '②10~100억', '③100~500억', '④500~1000억', '⑤1000~5000억', '⑥5000억~1조', '⑦1조 이상'];
  $('#f-size').innerHTML += sizes.map((s) => `<option>${s}</option>`).join('');
  $('#f-sector').innerHTML = state.meta.sectors.map((s) => `<span class="chip" data-s="${esc(s)}">${esc(s)}</span>`).join('');
  $$('#f-sector .chip').forEach((c) => c.onclick = () => { const s = c.dataset.s; state.filters.sectors.has(s) ? state.filters.sectors.delete(s) : state.filters.sectors.add(s); renderScreener(); });
  ['#f-search', '#f-size', '#f-growth', '#f-profit', '#f-listed', '#f-rating', '#f-cols', '#f-include'].forEach((id) => $(id).oninput = renderScreener);
  $('#f-reset').onclick = () => { state.filters.sectors.clear(); ['#f-search', '#f-size', '#f-growth', '#f-profit', '#f-listed', '#f-rating'].forEach((id) => $(id).value = ''); $('#f-include').checked = true; renderScreener(); };
}
function filteredCompanies() {
  const q = $('#f-search').value.trim().toLowerCase(), size = $('#f-size').value, g = $('#f-growth').value, p = $('#f-profit').value, li = $('#f-listed').value, rt = $('#f-rating').value, inc = $('#f-include').checked;
  return state.screener.companies.map(enrich).filter((r) => {
    if (inc && !r.include_in_sector) return false;
    if (q && !(r.name.toLowerCase().includes(q) || (r.description || '').toLowerCase().includes(q) || (r.category || '').toLowerCase().includes(q))) return false;
    if (state.filters.sectors.size && !state.filters.sectors.has(r.sector)) return false;
    if (size && r.size_band !== size) return false;
    if (g === 'g' && !(r.revenue_growth > 0)) return false;
    if (g === 'd' && !(r.revenue_growth < 0)) return false;
    if (p === 'p' && !(r.op > 0)) return false;
    if (p === 'l' && !(r.op < 0)) return false;
    if (li !== '' && (r.listed == null || Number(r.listed) !== Number(li))) return false;
    if (rt) { const [k, v] = rt.split(':'); if (r['rating_' + k] !== v) return false; }
    return true;
  });
}
function renderScreener() {
  if (!state.screener) return;
  const y = state.screener.year;
  $$('#f-sector .chip').forEach((c) => c.classList.toggle('on', state.filters.sectors.has(c.dataset.s)));
  const rows = filteredCompanies();
  const { key, dir } = state.sort;
  rows.sort((a, b) => { let va = a[key], vb = b[key]; if (key === 'listed') { va = va == null ? null : +va; vb = vb == null ? null : +vb; } if (va == null && vb == null) return 0; if (va == null) return 1; if (vb == null) return -1; return (typeof va === 'string' ? va.localeCompare(vb) : va - vb) * dir; });
  $('#screener-count').textContent = `${rows.length}개 기업 (상장 ${rows.filter((r) => r.listed).length} · 비상장 ${rows.filter((r) => r.listed === false).length})`;
  const groups = COLSETS[$('#f-cols').value](y);
  const sum = (k) => rows.reduce((s, r) => s + (r[k] || 0), 0);
  const agg = { name: `∑ 선택 기업 합계`, revenue: sum('revenue'), revenue_prev: sum('revenue_prev'), cogs: sum('cogs'), cogs_prev: sum('cogs_prev'), sga: sum('sga'), sga_prev: sum('sga_prev'), op: sum('op'), op_prev: sum('op_prev'), net: sum('net'), assets: sum('assets'), liabilities: sum('liabilities'), equity: sum('equity'), inventory: sum('inventory'), inventory_prev: sum('inventory_prev'), nwc_plus: sum('nwc_plus'), nwc_minus: sum('nwc_minus'), rou_asset: sum('rou_asset'), lease_liab: sum('lease_liab'), cf_op: sum('cf_op'), cf_inv: sum('cf_inv'), cf_fin: sum('cf_fin') };
  agg.revenue_growth = agg.revenue_prev ? agg.revenue / agg.revenue_prev - 1 : null; agg.cogs_ratio = agg.revenue ? agg.cogs / agg.revenue : null; agg.cogs_ratio_prev = agg.revenue_prev ? agg.cogs_prev / agg.revenue_prev : null;
  agg.sga_ratio = agg.revenue ? agg.sga / agg.revenue : null; agg.sga_ratio_prev = agg.revenue_prev ? agg.sga_prev / agg.revenue_prev : null; agg.opm = agg.revenue ? agg.op / agg.revenue : null; agg.opm_prev = agg.revenue_prev ? agg.op_prev / agg.revenue_prev : null;
  agg.op_change = agg.op - agg.op_prev; agg.net_margin = agg.revenue ? agg.net / agg.revenue : null; agg.debt_ratio = agg.equity ? (agg.liabilities - agg.lease_liab) / agg.equity : null; agg.net_cash = agg.nwc_plus - agg.nwc_minus;
  const avgInv = (agg.inventory + agg.inventory_prev) / 2; agg.inventory_turnover = avgInv ? agg.cogs / avgInv : null; agg.inventory_days = agg.inventory_turnover ? 365 / agg.inventory_turnover : null;
  agg.sga_items = {}; SGA.forEach((k) => { const s = rows.reduce((a, r) => a + (r.sga_items?.[k]?.cur || 0), 0); agg.sga_items[k] = { ratio: agg.revenue ? s / agg.revenue : null }; });
  enrich(agg); Object.assign(agg, ratingsOf(agg));
  const th = (label, k, extra = '') => `<th class="sortable ${key === k ? 'sorted' + (dir > 0 ? ' asc' : '') : ''} ${extra}" data-k="${k}">${label}</th>`;
  const th2 = (label, k, extra = '') => th(label, k, extra).replace('<th ', '<th rowspan="2" ');
  const head1 = `<tr><th rowspan="2">#</th>${th2('기업명', 'name', 'l')}${th2('상장', 'listed', 'l')}${th2('업종', 'sector', 'l')}<th rowspan="2" class="l" title="성장성 · 수익성 · 안정성">평가 <span class="muted">성장·수익·안정</span></th>${groups.map((g) => `<th class="group" colspan="${g.cols.length}">${g.g}</th>`).join('')}</tr>`;
  const head2 = `<tr>${groups.map((g) => g.cols.map((c, i) => th(c[0], c[1], i === 0 ? 'group-start' : '')).join('')).join('')}</tr>`;
  const row = (r, i, cls = '') => `<tr class="${cls || 'clickable'}" data-id="${r.id ?? ''}"><td>${i}</td><td class="l name">${esc(r.name)}${(r.description || (r.category && r.category !== r.sector)) ? `<div class="sub-text">${esc(r.description || r.category)}</div>` : ''}</td><td class="l">${cls ? '' : listedChip(r)}</td><td class="l">${esc(r.sector || '')}</td><td class="l">${ratingsCompact(r)}</td>${groups.map((g) => g.cols.map((c, j) => `<td class="${j === 0 ? 'group-start' : ''}">${c[2](r[c[1]])}</td>`).join('')).join('')}</tr>`;
  $('#tbl-screener').innerHTML = `<thead>${head1}${head2}</thead><tbody>${row({ ...agg, sector: `${rows.length}개사`, description: '' }, '', 'total')}${rows.map((r, i) => row(r, i + 1)).join('')}</tbody>`;
  $$('#tbl-screener th.sortable').forEach((t) => t.onclick = () => { const k = t.dataset.k; state.sort = { key: k, dir: state.sort.key === k ? -state.sort.dir : (k === 'name' || k === 'sector' ? 1 : -1) }; renderScreener(); });
  $$('#tbl-screener tr.clickable').forEach((tr) => tr.onclick = () => openCompany(+tr.dataset.id));
  $$('#tbl-screener tr.clickable').forEach((tr) => { tr.querySelectorAll('.name').forEach((td) => td.title = '기업분석 보기'); });
}
function ratingsOf(m) {
  const g = m.revenue_growth, p = m.opm, d = m.debt_ratio;
  return { rating_growth: g == null ? '-' : g > 0.2 ? 'Good' : g < 0 ? 'Bad' : 'N', rating_profit: p == null ? '-' : p > 0.15 ? 'Good' : p < 0.05 ? 'Bad' : 'N', rating_stability: (m.equity != null && m.equity <= 0) ? 'Bad' : d == null ? '-' : d < 1 ? 'Good' : d > 2 ? 'Bad' : 'N' };
}

/* ================= 기업분석 ================= */
/** 입력창 아래에 붙는 자동완성 드롭다운. items: 스크리너 기업 목록, onPick(company) */
function makeAutocomplete(input, getItems, onPick) {
  const wrap = input.parentElement;
  const list = document.createElement('div'); list.className = 'ac-list'; wrap.appendChild(list);
  let active = -1, matches = [];
  const hl = (name, q) => { const i = name.toLowerCase().indexOf(q); return i < 0 || !q ? esc(name) : esc(name.slice(0, i)) + '<b>' + esc(name.slice(i, i + q.length)) + '</b>' + esc(name.slice(i + q.length)); };
  const render = () => {
    const q = input.value.trim().toLowerCase();
    const items = getItems();
    matches = items.filter((c) => !q || c.name.toLowerCase().includes(q) || (c.description || '').toLowerCase().includes(q) || (c.sector || '').toLowerCase().includes(q) || (c.category || '').toLowerCase().includes(q));
    if (q) matches.sort((a, b) => (b.name.toLowerCase().startsWith(q) - a.name.toLowerCase().startsWith(q)) || (b.revenue || 0) - (a.revenue || 0));
    matches = matches.slice(0, 40);
    active = matches.length ? 0 : -1;
    list.innerHTML = matches.length ? matches.map((c, i) => `<div class="ac-item ${i === active ? 'active' : ''}" data-i="${i}"><span class="nm">${hl(c.name, q)}</span>${listedChip(c)}<span class="sec">${esc(c.sector || '')}</span>${c.description ? `<span class="desc">${esc(c.description)}</span>` : ''}</div>`).join('') : '<div class="ac-empty">검색 결과 없음</div>';
    list.classList.add('open');
  };
  const close = () => { list.classList.remove('open'); active = -1; };
  const pick = (i) => { const c = matches[i]; if (!c) return; close(); onPick(c); };
  input.addEventListener('focus', render);
  input.addEventListener('input', render);
  input.addEventListener('keydown', (e) => {
    if (!list.classList.contains('open')) { if (e.key === 'ArrowDown') render(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); if (!matches.length) return;
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length;
      $$('.ac-item', list).forEach((el, i) => el.classList.toggle('active', i === active));
      $$('.ac-item', list)[active]?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') { e.preventDefault(); pick(active); }
    else if (e.key === 'Escape') { close(); input.blur(); }
  });
  list.addEventListener('mousedown', (e) => { const it = e.target.closest('.ac-item'); if (it) { e.preventDefault(); pick(+it.dataset.i); } });
  input.addEventListener('blur', () => setTimeout(close, 120));
  document.addEventListener('click', (e) => { if (!wrap.contains(e.target)) close(); });
}

function bindCompany() {
  const items = () => state.screener.companies;
  makeAutocomplete($('#c-search'), items, (c) => { $('#c-search').value = c.name; openCompany(c.id); });
  makeAutocomplete($('#c-peer-input'), () => items().filter((x) => x.id !== state.company?.id && !state.peers.includes(x.id)), (c) => {
    $('#c-peer-input').value = '';
    if (state.peers.length >= 3) return;
    state.peers.push(c.id); renderPeerChips(); if (state.company) loadCompany(state.company.id);
  });
  const h = location.hash.match(/company\/(\d+)/); if (h) openCompany(+h[1]);
}
function renderPeerChips() {
  $('#c-peers').innerHTML = state.peers.map((id) => { const c = state.screener.companies.find((x) => x.id === id); return `<span class="chip on" data-id="${id}">${esc(c?.name || id)} ✕</span>`; }).join('');
  $$('#c-peers .chip').forEach((ch) => ch.onclick = () => { state.peers = state.peers.filter((i) => i !== +ch.dataset.id); renderPeerChips(); if (state.company) loadCompany(state.company.id); });
}
function openCompany(id) { showView('company'); loadCompany(id); }
async function loadCompany(id) {
  const c = state.screener.companies.find((x) => x.id === id);
  if (!c) return;
  state.company = c; $('#c-search').value = c.name; location.hash = `company/${id}`;
  if (!state.peers.length) { // 기본 비교: 같은 업종 매출 상위 2개
    state.peers = state.screener.companies.filter((x) => x.sector === c.sector && x.id !== id && x.include_in_sector).sort((a, b) => (b.revenue || 0) - (a.revenue || 0)).slice(0, 2).map((x) => x.id);
    renderPeerChips();
  }
  const d = await api(`/api/company/${id}?${qp()}&peers=${state.peers.join(',')}`);
  state.companyData = d; renderCompany(d);
}
function renderCompany(d) {
  const m = d.company, y = d.year, py = y - 1;
  const cols = SERIES();
  const stmt = d.statement;
  const html = `
  <div class="card"><div class="company-head"><h2>${esc(m.name)}</h2>${listedChip(m)}<span class="chip">${esc(m.sector || '')}${m.category && m.category !== m.sector ? ' · ' + esc(m.category) : ''}</span>${m.description ? `<span class="desc">${esc(m.description)}</span>` : ''}<span style="flex:1"></span>${ratings(m)}</div></div>
  <div class="grid kpi mt">
    ${[['매출액', fmtN(m.revenue), `${L(py)} ${fmtN(m.revenue_prev)} · ${fmtP(m.revenue_growth, 1, true)}`], ['영업이익', fmtN(m.op), `이익률 ${fmtP(m.opm)} (${L(py)} ${fmtP(m.opm_prev)})`], ['당기순이익', fmtN(m.net), `순이익률 ${fmtP(m.net_margin)}`], ['부채비율', fmtP(m.debt_ratio, 0), `${L(py)} ${fmtP(m.debt_ratio_prev, 0)} · 리스부채 제외`], ['재고보유일수', m.inventory_days != null ? fmtN(m.inventory_days) + '<span class="muted" style="font-size:13px">일</span>' : fmtN(null), `회전율 ${fmtN(m.inventory_turnover, 1)}회`], ['순가용현금', fmtN(m.net_cash), `순운전자본+ ${fmtN(m.nwc_plus)} − ${fmtN(m.nwc_minus)}`]].map(([t, v, s]) => `<div class="card tile"><h3>${t}</h3><div class="value">${v}</div><div class="sub">${s}</div></div>`).join('')}
  </div>
  <div class="grid two mt">
    <div class="card"><h3>손익계산서<small>억원 · 비율은 매출 대비</small></h3><div class="table-wrap"><table>
      <thead><tr><th class="l">계정</th><th>${L(py)}</th><th>${L(y)}</th><th>${GL()}</th><th class="group-start">${L(py)} 비율</th><th>${L(y)} 비율</th><th>GAP</th></tr></thead><tbody>
      ${stmt.map((r) => `<tr class="${r.is_sub ? 'sub' : ''}"><td class="l">${esc(r.category)}</td><td>${fmtN(r.prev)}</td><td>${fmtN(r.cur)}</td><td>${fmtP(r.growth, 1, true)}</td><td class="group-start">${fmtP(r.ratio_prev)}</td><td>${fmtP(r.ratio_cur)}</td><td>${fmtPp(r.gap)}</td></tr>`).join('')}
      </tbody></table></div>
      <h3 class="mt">재무상태 · 현금흐름</h3><div class="table-wrap"><table><thead><tr><th class="l">계정</th><th>${L(py)}</th><th>${L(y)}</th><th>증감률</th></tr></thead><tbody>
      ${d.balance.map((r) => `<tr><td class="l">${esc(r.category)}</td><td>${r.is_ratio ? fmtP(r.prev, 0) : fmtN(r.prev)}</td><td>${r.is_ratio ? fmtP(r.cur, 0) : fmtN(r.cur)}</td><td>${fmtP(r.growth, 1, true)}</td></tr>`).join('')}
      </tbody></table></div>
    </div>
    <div>
      ${SGA.some((k) => m.sga_items[k]?.cur != null || m.sga_items[k]?.prev != null) ? `<div class="card"><h3>판관비 구성<small>매출 대비 비율, ${L(py)} vs ${L(y)}</small></h3><div class="chart-box tall"><canvas id="ch-c-sga"></canvas></div></div>` : `<div class="card"><h3>판관비 구성</h3><div class="note">${state.period === 'FY' ? '판관비 세부 항목 데이터가 없습니다' : '판관비 세부 항목은 연간 데이터에서만 제공됩니다 (DART 분기보고서 미제공)'}</div></div>`}
      <div class="card mt"><h3>연도별 매출 · 영업이익<small>억원 · 연간</small></h3><div class="chart-box"><canvas id="ch-c-trend"></canvas></div></div>
      ${d.quarterly.length ? `<div class="card mt"><h3>분기별 매출 · 영업이익<small>억원 · 4분기는 연간 − 1~3분기</small></h3><div class="chart-box"><canvas id="ch-c-quarter"></canvas></div></div>` : ''}
      <div class="card mt"><h3>판관비 세부 항목<small>${state.period === 'FY' ? L(y) + ' · 원장 기준' : '연간 데이터에서만 제공'}</small></h3>
        ${Object.entries(d.sga_detail).map(([k, items]) => `<details class="sga"><summary>${esc(k)} <span class="muted">(${items.length}개 항목 · ${fmtN(items.reduce((s, i) => s + (i.cur || 0), 0))}억)</span></summary><div class="table-wrap"><table><thead><tr><th class="l">항목</th><th>${L(py)}</th><th>${L(y)}</th><th>증감률</th></tr></thead><tbody>${items.map((i) => `<tr><td class="l">${esc(i.item)}</td><td>${fmtN(i.prev, 1)}</td><td>${fmtN(i.cur, 1)}</td><td>${fmtP(i.prev ? i.cur / i.prev - 1 : null, 1, true)}</td></tr>`).join('')}</tbody></table></div></details>`).join('') || '<div class="note">세부 항목 없음</div>'}
      </div>
    </div>
  </div>
  <div class="card mt"><h3>비교<small>${L(y)} · 비교 기업 / 업종 합계 / 전체 합계 (합계 기준 비율)</small></h3>
    <div class="table-wrap"><table id="tbl-compare"></table></div>
    <div class="chart-box mt"><canvas id="ch-c-compare"></canvas></div>
  </div>`;
  $('#company-body').innerHTML = html;

  const keys = SGA.filter((k) => m.sga_items[k]?.cur != null || m.sga_items[k]?.prev != null);
  if (keys.length) chart('ch-c-sga', { type: 'bar', data: { labels: keys.map((k) => k.replace(/^.\s?/, '')), datasets: [{ label: `${L(py)}`, data: keys.map((k) => m.sga_items[k].ratio_prev), backgroundColor: css('--border'), ...barStyle }, { label: `${L(y)}`, data: keys.map((k) => m.sga_items[k].ratio), backgroundColor: cols[0], ...barStyle }] },
    options: { indexAxis: 'y', scales: { x: { ticks: { callback: pctTick } }, y: { grid: { display: false } } }, plugins: { legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label} ${(c.raw * 100).toFixed(2)}%  (${fmtN(m.sga_items[keys[c.dataIndex]][c.datasetIndex ? 'cur' : 'prev'])}억)`.replace(/<[^>]+>/g, '') } } } } });
  chart('ch-c-trend', { type: 'bar', data: { labels: d.trend.map((t) => t.year + '년'), datasets: [{ label: '매출액', data: d.trend.map((t) => t.revenue), backgroundColor: cols[0], ...barStyle }, { label: '영업이익', data: d.trend.map((t) => t.op), backgroundColor: cols[1], ...barStyle }] },
    options: { scales: { y: { ticks: { callback: (v) => v.toLocaleString() } }, x: { grid: { display: false } } }, plugins: { legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label} ${fmtN(c.raw)}억`.replace(/<[^>]+>/g, '') } } } } });

  if (d.quarterly.length) {
    chart('ch-c-quarter', { type: 'bar', data: { labels: d.quarterly.map((q) => q.label), datasets: [{ label: '매출액', data: d.quarterly.map((q) => q.revenue), backgroundColor: cols[0], ...barStyle }, { label: '영업이익', data: d.quarterly.map((q) => q.op), backgroundColor: cols[1], ...barStyle }] },
      options: { scales: { y: { ticks: { callback: (v) => v.toLocaleString() } }, x: { grid: { display: false } } }, plugins: { legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label} ${fmtN(c.raw)}억 (영업이익률 ${((d.quarterly[c.dataIndex].opm || 0) * 100).toFixed(1)}%)`.replace(/<[^>]+>/g, '') } } } } });
  }
  const comp = [{ ...m, _label: m.name + listedChip(m), _plain: m.name }, ...d.peers.map((p) => ({ ...p, _label: p.name + listedChip(p), _plain: p.name })), ...(d.sector_avg ? [{ ...d.sector_avg, _label: `업종 합계 (${d.sector_avg.sector})`, _plain: `업종 합계 (${d.sector_avg.sector})` }] : []), ...(d.total_avg ? [{ ...d.total_avg, _label: '전체 합계', _plain: '전체 합계' }] : [])];
  const metrics = [['매출액', 'revenue', fmtN], [`매출${GL()}`, 'revenue_growth', (v) => fmtP(v, 1, true)], ['매출원가율', 'cogs_ratio', fmtP], ['판관비율', 'sga_ratio', fmtP], ['영업이익', 'op', fmtN], ['영업이익률', 'opm', fmtP], ['순이익률', 'net_margin', fmtP], ...SGA.map((k) => [k, 'sga_' + k, fmtP]), ['부채비율', 'debt_ratio', (v) => fmtP(v, 0)], ['재고보유일수', 'inventory_days', fmtN], ['순가용현금', 'net_cash', fmtN]];
  comp.forEach(enrich);
  $('#tbl-compare').innerHTML = `<thead><tr><th class="l">지표</th>${comp.map((c) => `<th>${c._label}</th>`).join('')}</tr></thead><tbody><tr><td class="l">간략 평가</td>${comp.map((c) => `<td>${ratings(c)}</td>`).join('')}</tr>${metrics.map(([l, k, f]) => `<tr><td class="l">${esc(l)}</td>${comp.map((c) => `<td>${f(c[k])}</td>`).join('')}</tr>`).join('')}</tbody>`;
  const ck = ['cogs_ratio', 'sga_ratio', 'opm', 'sga_① 인건비', 'sga_④ 광고선전비', 'sga_③ 지급/용역수수료', 'sga_⑦ 물류/운반비'];
  chart('ch-c-compare', { type: 'bar', data: { labels: ['매출원가율', '판관비율', '영업이익률', '인건비율', '광고비율', '수수료율', '물류비율'], datasets: comp.map((c, i) => ({ label: c._plain, data: ck.map((k) => c[k]), backgroundColor: cols[i % cols.length], ...barStyle })) },
    options: { scales: { y: { ticks: { callback: pctTick } }, x: { grid: { display: false } } }, plugins: { legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label} ${(c.raw * 100).toFixed(1)}%` } } } } });
}

/* ================= 데이터 ================= */
function bindData() {
  const run = (src) => async () => { $$('#view-data .btn').forEach((b) => b.disabled = true); await api(`/api/refresh?source=${src}`, { method: 'POST' }); await new Promise((r) => setTimeout(r, 800)); await loadData(); $$('#view-data .btn').forEach((b) => b.disabled = false); };
  $('#btn-refresh-all').onclick = run('all'); $('#btn-refresh-inbox').onclick = run('inbox'); $('#btn-refresh-dart').onclick = run('dart');
  $('#upload-form').onsubmit = async (e) => {
    e.preventDefault(); const f = $('#upload-file').files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f); $('#upload-result').textContent = '업로드 중…';
    try { const r = await api('/api/upload', { method: 'POST', body: fd }); $('#upload-result').textContent = `완료: ${r.saved} → ${JSON.stringify(r.result)}`; await loadMeta(); await loadAll(); await loadData(); }
    catch (err) { $('#upload-result').textContent = '오류: ' + err.message; }
  };
}
let dataPoll = null;
async function loadData() {
  const s = await api('/api/refresh/status');
  $('#data-status').innerHTML = `<table><tbody>
    <tr><td class="l muted">상태</td><td class="l">${s.running ? '<span class="log-status running">갱신 진행 중…</span>' : '대기'}</td></tr>
    <tr><td class="l muted">스케줄</td><td class="l">${s.schedule ? `<code>${esc(s.schedule)}</code> (cron)` : '자동 갱신 꺼짐'}</td></tr>
    <tr><td class="l muted">다음 실행</td><td class="l">${s.next_run ? s.next_run.replace('T', ' ').slice(0, 19) : '–'}</td></tr>
    <tr><td class="l muted">DART 연동</td><td class="l">${s.dart_enabled ? '<span class="pos">사용 (API 키 설정됨)</span>' : '<span class="muted">미설정 – .env 에 DART_API_KEY 입력</span>'}</td></tr>
    <tr><td class="l muted">기준 기간</td><td class="l">${L(state.year)}</td></tr></tbody></table>`;
  $('#tbl-log').innerHTML = `<thead><tr><th>#</th><th class="l">소스</th><th class="l">시작</th><th class="l">종료</th><th class="l">상태</th><th>행 수</th><th class="l">메시지</th></tr></thead><tbody>${s.logs.map((l) => `<tr><td>${l.id}</td><td class="l">${esc(l.source)}</td><td class="l">${l.started_at}</td><td class="l">${l.finished_at || ''}</td><td class="l"><span class="log-status ${l.status}">${l.status}</span></td><td>${l.rows_written ?? ''}</td><td class="l"><pre class="msg">${esc(l.message || '')}</pre></td></tr>`).join('') || '<tr><td colspan="7" class="l muted">이력 없음</td></tr>'}</tbody>`;
  $('#tbl-files').innerHTML = `<thead><tr><th class="l">파일</th><th class="l">임포트 시각</th><th>크기</th></tr></thead><tbody>${s.files.map((f) => `<tr><td class="l">${esc(f.path.split('/').pop())}</td><td class="l">${f.imported_at}</td><td>${(f.size / 1024).toFixed(0)} KB</td></tr>`).join('') || '<tr><td colspan="3" class="l muted">data/inbox 에 엑셀 파일을 넣거나 위에서 업로드하세요</td></tr>'}</tbody>`;
  if (s.running && !dataPoll) dataPoll = setInterval(async () => { const st = await api('/api/refresh/status?limit=1'); if (!st.running) { clearInterval(dataPoll); dataPoll = null; await loadMeta(); await loadAll(); await loadData(); } }, 2000);
}

init().catch((e) => { console.error(e); $('main').insertAdjacentHTML('afterbegin', `<div class="card"><b>오류:</b> ${esc(e.message)}</div>`); });
