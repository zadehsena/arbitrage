const tabs = [...document.querySelectorAll('.tab')];
const tableWrap = document.querySelector('#table-wrap');
const meta = document.querySelector('#meta');
const notice = document.querySelector('#notice');
const refresh = document.querySelector('#refresh');
const home = document.querySelector('#home');
const matchSummary = document.querySelector('#match-summary');
let activeSport = null;
let activeLeagues = [];
let activeLabel = '';
let latestRecords = [];
let nextSportOffset = null;
let sportRecordTotal = 0;
const refreshingSports = new Set();
const oddsRefreshIntervalMs = 60_000;
const sportPageSize = 25;
const walletRefreshIntervalMs = 30_000;
let walletRefreshInFlight = false;

const price = value => value == null ? '—' : `$${Number(value).toFixed(3)}`;
const safe = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const startTime = value => value ? new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value)) : 'Time unavailable';

function initials(name) {
  return String(name || '?').split(/\s+/).slice(0, 2).map(word => word[0]).join('').toUpperCase();
}

function teamMarkup(team) {
  const name = team.name || 'Unknown team';
  const subtitle = team.record || '';
  const image = team.logo ? `<img src="${safe(team.logo)}" alt="" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false">` : '';
  return `<div class="team"><span class="team-logo">${image}<b${team.logo ? ' hidden' : ''}>${safe(initials(name))}</b></span><span>${safe(name)}<small>${safe(subtitle)}</small></span></div>`;
}

function teamsForRecord(record) {
  if (record.teams?.length) return record.teams;
  // Older cached reports predate the team metadata. Preserve the same two-row
  // layout while using initials until the user refreshes the data for logos.
  return String(record.kalshi_title || '').split(/\s+vs\.?\s+/i)
    .filter(Boolean).map(name => ({ name }));
}

const mlbTeamAliases = {
  arizona: 'diamondbacks', atlanta: 'braves', baltimore: 'orioles', boston: 'redsox',
  chicagoc: 'cubs', chicagows: 'whitesox', cincinnati: 'reds', cleveland: 'guardians',
  colorado: 'rockies', detroit: 'tigers', houston: 'astros', kansascity: 'royals',
  laangels: 'angels', losangelesa: 'angels', ladodgers: 'dodgers', losangelesd: 'dodgers',
  miami: 'marlins', milwaukee: 'brewers',
  minnesota: 'twins', newyorkm: 'mets', newyorky: 'yankees', oakland: 'athletics',
  philadelphia: 'phillies', pittsburgh: 'pirates', sandiego: 'padres',
  sanfrancisco: 'giants', seattle: 'mariners', stlouis: 'cardinals',
  tampabay: 'rays', texas: 'rangers', toronto: 'bluejays', washington: 'nationals',
};

// The two venues occasionally use an abbreviation on one side and a city name
// on the other. Keep those labels in the same team slot.
const teamAliases = {
  nmstate: 'newmexicost',
  fcdallas: 'dallas',
  realsaltlake: 'saltlake',
  pitsteelers: 'pittsburgh',
  clebrowns: 'cleveland',
  indcolts: 'indianapolis',
  wascommanders: 'washington',
  aricardinals: 'arizona',
  nygiants: 'newyorkg',
  nepatriots: 'newengland',
  bufbills: 'buffalo',
  nyjets: 'newyorkj',
  chibears: 'chicago',
  dalcowboys: 'dallas',
  houtexans: 'houston',
  larams: 'losangelesr',
  phieagles: 'philadelphia',
  gbpackers: 'greenbay',
  tbbuccaneers: 'tampabay',
  tentitans: 'tennessee',
  balravens: 'baltimore',
  jacjaguars: 'jacksonville',
  cinbengals: 'cincinnati',
  miadolphins: 'miami',
  minvikings: 'minnesota',
  kcchiefs: 'kansascity',
  lvraiders: 'lasvegas',
  lachargers: 'losangelesc',
  seaseahawks: 'seattle',
  denbroncos: 'denver',
  sf49ers: 'sanfrancisco',
  detlions: 'detroit',
  carpanthers: 'carolina',
  atlfalcons: 'atlanta',
  nosaints: 'neworleans',
};

function normalizeTeam(value) {
  const normalized = String(value || '').toLowerCase().replace(/\bwins?\b/g, '').replace(/[^a-z0-9]/g, '');
  if (activeSport === 'baseball') return mlbTeamAliases[normalized] || normalized;
  return teamAliases[normalized] || normalized;
}

function orderedBookItems(record, items, labelField) {
  const unused = [...items];
  const ordered = teamsForRecord(record).map(team => {
    const name = normalizeTeam(team.name);
    const index = unused.findIndex(item => {
      const label = normalizeTeam(item[labelField]);
      return label === name || label.startsWith(name) || name.startsWith(label);
    });
    return index >= 0 ? unused.splice(index, 1)[0] : null;
  });
  while (ordered.length < 2) ordered.push(unused.shift() || null);
  // Only soccer has a draw outcome. Every other sport on this dashboard is a
  // two-way winner market, so never let an unmatched label create a third tile.
  if (activeSport !== 'soccer') return ordered.slice(0, 2);
  const drawIndex = unused.findIndex(item => /^(draw|tie)/i.test(String(item[labelField])));
  if (drawIndex >= 0) {
    const draw = unused.splice(drawIndex, 1)[0];
    // Three-way sports markets always read: first team, draw, second team.
    return [ordered[0], draw, ordered[1]];
  }
  return ordered.slice(0, 2);
}

function pairForBook(record, items, labelField, priceField, venueUrl, venueName) {
  const ordered = orderedBookItems(record, items, labelField);
  const tiles = ordered.map(item => {
    if (!item) return '<span class="outcome-tile"><span class="price unavailable">—</span></span>';
    const value = Number(item[priceField]);
    const tone = Number.isFinite(value) && value < 0.5 ? 'down' : 'up';
    return `<span class="outcome-tile"><span class="price ${tone}" title="${safe(item[labelField])}">${price(item[priceField])}</span></span>`;
  }).join('');
  if (!venueUrl) return `<div class="book-pair">${tiles}</div>`;
  return `<a class="book-link" href="${safe(venueUrl)}" target="_blank" rel="noopener noreferrer" aria-label="Open this event on ${safe(venueName)}"><span class="book-pair">${tiles}</span></a>`;
}

function numericQuote(value) {
  // A missing quote is not a zero-cost outcome. Treat null, undefined, and an
  // empty string as unavailable before doing any arbitrage arithmetic.
  if (value == null || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function arbitrageCell(record) {
  const kalshi = orderedBookItems(record, record.kalshi_moneyline_asks, 'contract')
    .map(item => numericQuote(item?.yes_ask));
  const polymarket = orderedBookItems(record, record.polymarket_us_displayed_moneyline_quotes, 'outcome')
    .map(item => numericQuote(item?.displayed_quote));
  if (kalshi.length !== 2 || polymarket.length !== 2) return '<span class="no-arb">3-way review</span>';
  if ([...kalshi, ...polymarket].some(quote => quote == null)) {
    return '<span class="no-arb">Incomplete</span>';
  }
  const totals = [kalshi[0] + polymarket[1], kalshi[1] + polymarket[0]].filter(Number.isFinite);
  const bestTotal = Math.min(...totals);
  if (!Number.isFinite(bestTotal) || bestTotal >= 1) return '<span class="no-arb">—</span>';
  return `<div class="arb"><strong>+${((1 - bestTotal) * 100).toFixed(2)}%</strong></div>`;
}

function renderSport(data, append = false) {
  const pageRecords = data.records || [];
  latestRecords = append ? [...latestRecords, ...pageRecords] : pageRecords;
  nextSportOffset = data.next_offset;
  sportRecordTotal = data.total_records ?? latestRecords.length;
  const records = latestRecords;
  tableWrap.classList.remove('home-layout');
  const sportName = activeLabel || data.sport[0].toUpperCase() + data.sport.slice(1);
  document.querySelector('#sport-title').textContent = sportName;
  matchSummary.textContent = `${sportRecordTotal} matched ${sportName.toLowerCase()} games`;
  document.querySelector('#sidebar-updated').textContent = `Updated ${new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date())}`;
  meta.textContent = data.kalshi_events_compared
    ? `Compared ${data.kalshi_events_compared} Kalshi and ${data.polymarket_events_compared} Polymarket US events`
    : '';
  notice.hidden = false;
  notice.textContent = data.quote_notice || 'Prices must be verified against each venue’s live executable order book and fees.';
  if (!records.length) { tableWrap.innerHTML = `<div class="empty"><h2>No matched ${safe(sportName.toLowerCase())} games</h2><p>There are no likely open cross-venue matches in the latest public feeds. Refresh to check again.</p></div>`; return; }
  const loadMore = nextSportOffset == null ? '' : `<div class="load-more"><button id="load-more" type="button">Load 25 more <span>Showing ${records.length} of ${sportRecordTotal}</span></button></div>`;
  tableWrap.innerHTML = `<table class="${activeSport === 'soccer' ? 'three-way-table' : ''}"><colgroup><col class="game-column"><col class="time-column"><col class="book-column"><col class="book-column"><col class="book-column"><col class="book-column"><col class="arbitrage-column"></colgroup><thead><tr><th>Game / Event</th><th>Start time</th><th><span class="book-heading"><b class="venue-icon kalshi">K</b>Kalshi</span></th><th><span class="book-heading"><b class="venue-icon polymarket">◇</b>Polymarket US</span></th><th><span class="book-heading"><b class="venue-icon novig">N</b>Novig</span></th><th><span class="book-heading"><b class="venue-icon prophetx">P</b>ProphetX</span></th><th>Arbitrage</th></tr></thead><tbody>${records.map((record, index) => `<tr class="game-row" data-game-index="${index}" tabindex="0" role="link" aria-label="Open ${safe(record.kalshi_title || 'game')} market breakdown">
    <td><div class="game-teams">${teamsForRecord(record).map(teamMarkup).join('')}</div></td>
    <td><span class="start">${safe(startTime(record.start_time))}</span></td>
    <td>${pairForBook(record, record.kalshi_moneyline_asks, 'contract', 'yes_ask', record.kalshi_url, 'Kalshi')}</td>
    <td>${pairForBook(record, record.polymarket_us_displayed_moneyline_quotes, 'outcome', 'displayed_quote', record.polymarket_us_url, 'Polymarket US')}</td>
    <td class="unavailable-book" aria-label="Novig data not connected"></td>
    <td class="unavailable-book" aria-label="ProphetX data not connected"></td>
    <td>${arbitrageCell(record)}</td>
  </tr>`).join('')}</tbody></table>${loadMore}`;
}

function walletCard(wallet) {
  const icons = { Kalshi: ['kalshi', 'K'], 'Polymarket US': ['polymarket', '◇'], Novig: ['novig', 'N'], ProphetX: ['prophetx', 'P'] };
  const [iconClass, icon] = icons[wallet.venue] || ['polymarket', '◇'];
  if (wallet.placeholder) {
    return `<article class="wallet-card wallet-placeholder"><div class="wallet-heading"><b class="venue-icon ${iconClass}">${icon}</b><span>${safe(wallet.venue)}</span><em>Placeholder</em></div><strong>—</strong><span>Wallet integration coming soon</span></article>`;
  }
  const balance = wallet.balance == null ? 'Unavailable' : `$${Number(wallet.balance).toFixed(2)}`;
  const portfolio = wallet.portfolio_value == null ? '' : `<small>Portfolio value ${safe(`$${Number(wallet.portfolio_value).toFixed(2)}`)}</small>`;
  const state = wallet.connected ? 'Connected' : 'Reconnect required';
  return `<article class="wallet-card"><div class="wallet-heading"><b class="venue-icon ${iconClass}">${icon}</b><span>${safe(wallet.venue)}</span><em class="${wallet.connected ? 'connected' : ''}">${state}</em></div><strong>${balance}</strong><span>Wallet balance</span>${portfolio}</article>`;
}

function renderHome(data, opportunityData = {}) {
  const wallets = data.wallets || [];
  const opportunities = opportunityData.opportunities || [];
  const sportCounts = opportunityData.sport_counts || {};
  latestRecords = [];
  nextSportOffset = null;
  sportRecordTotal = 0;
  tableWrap.classList.add('home-layout');
  document.querySelector('#sport-title').textContent = 'Dashboard';
  matchSummary.textContent = '';
  document.querySelector('#sidebar-updated').textContent = `Updated ${new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(data.updated_at || Date.now()))}`;
  meta.textContent = 'Connected wallet balances · auto-refreshes every 30s';
  notice.hidden = true;
  const quotePair = (quotes, url, venue) => {
    const pair = `<span class="book-pair"><span class="price ${Number(quotes?.[0]) < .5 ? 'down' : 'up'}">${price(quotes?.[0])}</span><span class="price ${Number(quotes?.[1]) < .5 ? 'down' : 'up'}">${price(quotes?.[1])}</span></span>`;
    return url ? `<a class="book-link" href="${safe(url)}" target="_blank" rel="noopener noreferrer" aria-label="Open this event on ${safe(venue)}">${pair}</a>` : pair;
  };
  const opportunitiesTable = opportunities.length ? opportunities.map(row => `<tr><td>${row.teams?.length ? `<div class="game-teams">${row.teams.map(teamMarkup).join('')}</div>` : `<span class="game">${safe(row.title)}</span>`}</td><td><span class="start">${safe(startTime(row.start_time))}</span></td><td>${quotePair(row.kalshi, row.kalshi_url, 'Kalshi')}</td><td>${quotePair(row.polymarket_us, row.polymarket_us_url, 'Polymarket US')}</td><td class="unavailable-book"></td><td class="unavailable-book"></td><td>${row.edge ? `<div class="arb"><strong>+${(row.edge * 100).toFixed(2)}%</strong></div>` : '<span class="no-arb">—</span>'}</td></tr>`).join('') : '<tr><td colspan="7" class="detail-empty">No current opportunities in cached reports. Select a sport and refresh its data.</td></tr>';
  const total = Object.values(sportCounts).reduce((sum, count) => sum + count, 0);
  const sportList = Object.entries(sportCounts).filter(([, count]) => count).sort((a, b) => b[1] - a[1]).map(([name, count]) => `<li><span>${safe(name)}</span><b>${count}</b></li>`).join('') || '<li><span>No report data yet</span></li>';
  tableWrap.innerHTML = `<section class="wallet-grid">${wallets.map(walletCard).join('')}</section><h2 class="home-section-title">Top Opportunities</h2><section class="opportunities"><div class="opportunity-table"><table><thead><tr><th>Game / Event</th><th>Start time</th><th><span class="book-heading"><b class="venue-icon kalshi">K</b>Kalshi</span></th><th><span class="book-heading"><b class="venue-icon polymarket">◇</b>Polymarket US</span></th><th><span class="book-heading"><b class="venue-icon novig">N</b>Novig</span></th><th><span class="book-heading"><b class="venue-icon prophetx">P</b>ProphetX</span></th><th>Arbitrage</th></tr></thead><tbody>${opportunitiesTable}</tbody></table></div></section><section class="sport-summary"><div class="summary-ring"><strong>${total}</strong><span>Games</span></div><div><h2>Opportunities by sport</h2><ul>${sportList}</ul></div></section>`;
}

async function loadHome() {
  if (activeSport || walletRefreshInFlight) return;
  walletRefreshInFlight = true;
  refresh.disabled = true;
  refresh.textContent = 'Refreshing…';
  try {
    const [walletResponse, opportunitiesResponse] = await Promise.all([fetch('/api/account-summary'), fetch('/api/opportunities')]);
    const [data, opportunityData] = await Promise.all([walletResponse.json(), opportunitiesResponse.json()]);
    if (!walletResponse.ok || !opportunitiesResponse.ok) throw new Error('Unable to load dashboard data');
    if (!activeSport) renderHome(data, opportunityData);
  } catch (error) {
    if (!activeSport) {
      meta.textContent = 'Wallet balances unavailable.';
      notice.textContent = 'Check your local account credentials and refresh.';
      tableWrap.innerHTML = `<section class="home-empty"><h2>Wallet balances unavailable</h2><p>${safe(error.message)}</p></section>`;
    }
  } finally {
    walletRefreshInFlight = false;
    if (!activeSport) {
      refresh.disabled = false;
      refresh.textContent = 'Refresh';
    }
  }
}

async function loadSport(refreshData = false, append = false) {
  const sport = activeSport;
  const leagues = [...activeLeagues];
  const offset = append ? nextSportOffset : 0;
  const selectionKey = `${sport}:${leagues.join(',')}`;
  if (!sport || (append && offset == null) || refreshingSports.has(selectionKey)) return;
  refreshingSports.add(selectionKey);
  refresh.disabled = true;
  refresh.textContent = refreshData ? 'Refreshing…' : 'Refresh data';
  try {
    const query = new URLSearchParams({ offset: String(offset), limit: String(sportPageSize) });
    if (leagues.length) query.set('leagues', leagues.join(','));
    const endpoint = `/api/sports/${sport}${refreshData ? '/refresh' : ''}?${query}`;
    const response = await fetch(endpoint, { method: refreshData ? 'POST' : 'GET' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Unable to load ${sport} data`);
    // Do not overwrite a newly selected tab with a slower previous request.
    if (activeSport === sport && activeLeagues.join(',') === leagues.join(',')) renderSport(data, append);
  } catch (error) {
    if (activeSport === sport && activeLeagues.join(',') === leagues.join(',')) {
      meta.textContent = `Could not load ${sport} data.`;
      tableWrap.innerHTML = `<div class="empty"><h2>Data unavailable</h2><p>${safe(error.message)}</p></div>`;
    }
  } finally {
    refreshingSports.delete(selectionKey);
    if (activeSport === sport && activeLeagues.join(',') === leagues.join(',')) {
      refresh.disabled = false;
      refresh.textContent = 'Refresh data';
    }
  }
}

document.querySelectorAll('.sport-group-toggle').forEach(toggle => toggle.addEventListener('click', () => {
  const options = document.querySelector(`#${toggle.getAttribute('aria-controls')}`);
  const willExpand = toggle.getAttribute('aria-expanded') !== 'true';
  document.querySelectorAll('.sport-group-toggle').forEach(other => {
    const otherOptions = document.querySelector(`#${other.getAttribute('aria-controls')}`);
    other.setAttribute('aria-expanded', 'false');
    otherOptions.hidden = true;
  });
  toggle.setAttribute('aria-expanded', String(willExpand));
  options.hidden = !willExpand;
}));

tabs.forEach(tab => tab.addEventListener('click', () => {
  activeSport = tab.dataset.sport;
  activeLeagues = tab.dataset.leagues.split(',');
  activeLabel = tab.dataset.label;
  tabs.forEach(item => item.classList.toggle('active', item === tab));
  document.querySelectorAll('.sport-group').forEach(group => group.classList.toggle('active', group.contains(tab)));
  home.classList.remove('active');
  refresh.hidden = false;
  loadSport();
}));
home.addEventListener('click', event => {
  event.preventDefault();
  activeSport = null;
  activeLeagues = [];
  activeLabel = '';
  home.classList.add('active');
  tabs.forEach(item => item.classList.remove('active'));
  document.querySelectorAll('.sport-group').forEach(group => group.classList.remove('active'));
  loadHome();
});
refresh.addEventListener('click', () => activeSport ? loadSport(true) : loadHome());
function openGameDetail(record, index) {
  const params = new URLSearchParams({
    sport: activeSport,
    kalshi: record.kalshi_event_ticker,
    polymarket: record.polymarket_us_event_slug,
  });
  if (activeLeagues.length) params.set('leagues', activeLeagues.join(','));
  params.set('offset', String(Math.floor(index / sportPageSize) * sportPageSize));
  window.location.assign(`/game.html?${params}`);
}
tableWrap.addEventListener('click', event => {
  if (event.target.closest('#load-more')) {
    loadSport(false, true);
    return;
  }
  const row = event.target.closest('.game-row');
  if (!row || event.target.closest('a')) return;
  const index = Number(row.dataset.gameIndex);
  openGameDetail(latestRecords[index], index);
});
tableWrap.addEventListener('keydown', event => {
  if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('.game-row')) {
    event.preventDefault();
    const index = Number(event.target.dataset.gameIndex);
    openGameDetail(latestRecords[index], index);
  }
});
document.querySelector('#search').addEventListener('input', event => {
  const query = event.target.value.trim().toLowerCase();
  document.querySelectorAll('#table-wrap tbody tr').forEach((row, index) => {
    const record = latestRecords[index];
    row.hidden = Boolean(query) && !JSON.stringify(record).toLowerCase().includes(query);
  });
});
setInterval(() => { document.querySelector('#clock').textContent = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' }).format(new Date()); }, 1000);
setInterval(() => {
  if (activeSport && !document.hidden) loadSport(true);
}, oddsRefreshIntervalMs);
setInterval(() => {
  if (!activeSport && !document.hidden) loadHome();
}, walletRefreshIntervalMs);
document.addEventListener('visibilitychange', () => {
  if (activeSport && !document.hidden) loadSport(true);
  if (!activeSport && !document.hidden) loadHome();
});
loadHome();
