const tabs = [...document.querySelectorAll('.tab')];
const tableWrap = document.querySelector('#table-wrap');
const meta = document.querySelector('#meta');
const notice = document.querySelector('#notice');
const refresh = document.querySelector('#refresh');
const home = document.querySelector('#home');
let activeSport = null;
let latestRecords = [];
const refreshingSports = new Set();
const oddsRefreshIntervalMs = 15_000;
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
  pitsteelers: 'pittsburgh',
  clebrowns: 'cleveland',
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
    const isDraw = /^(draw|tie)/i.test(String(item[labelField]));
    return `<span class="outcome-tile"><span class="price ${tone}" title="${safe(item[labelField])}">${price(item[priceField])}</span>${isDraw ? '<small>Draw</small>' : ''}</span>`;
  }).join('');
  if (!venueUrl) return `<div class="book-pair">${tiles}</div>`;
  return `<a class="book-link" href="${safe(venueUrl)}" target="_blank" rel="noopener noreferrer" aria-label="Open this event on ${safe(venueName)}"><span class="book-pair">${tiles}</span></a>`;
}

function arbitrageCell(record) {
  const kalshi = orderedBookItems(record, record.kalshi_moneyline_asks, 'contract')
    .map(item => Number(item?.yes_ask));
  const polymarket = orderedBookItems(record, record.polymarket_us_displayed_moneyline_quotes, 'outcome')
    .map(item => Number(item?.displayed_quote));
  if (kalshi.length !== 2 || polymarket.length !== 2) return '<span class="no-arb">3-way review</span>';
  const totals = [kalshi[0] + polymarket[1], kalshi[1] + polymarket[0]].filter(Number.isFinite);
  const bestTotal = Math.min(...totals);
  if (!Number.isFinite(bestTotal) || bestTotal >= 1) return '<span class="no-arb">—</span>';
  return `<div class="arb"><strong>+${((1 - bestTotal) * 100).toFixed(2)}%</strong><small>Unverified</small></div>`;
}

function renderSport(data) {
  const records = data.records || [];
  latestRecords = records;
  const sportName = data.sport[0].toUpperCase() + data.sport.slice(1);
  document.querySelector('#sport-title').innerHTML = `${safe(sportName)} <span>⌄</span>`;
  document.querySelector('#sidebar-updated').textContent = `Updated ${new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date())}`;
  meta.textContent = `${records.length} matched ${sportName.toLowerCase()} games${data.kalshi_events_compared ? ` · compared ${data.kalshi_events_compared} Kalshi and ${data.polymarket_events_compared} Polymarket US events` : ''} · auto-refreshes every 15s`;
  notice.textContent = data.quote_notice;
  if (!records.length) { tableWrap.innerHTML = `<div class="empty"><h2>No matched ${safe(sportName.toLowerCase())} games</h2><p>There are no likely open cross-venue matches in the latest public feeds. Refresh to check again.</p></div>`; return; }
  tableWrap.innerHTML = `<table><colgroup><col class="game-column"><col class="time-column"><col class="market-column"><col class="book-column"><col class="book-column"><col class="book-column"><col class="book-column"><col class="arbitrage-column"></colgroup><thead><tr><th>Game / Event</th><th>Start time</th><th>Market</th><th><span class="book-heading"><b class="venue-icon kalshi">K</b>Kalshi</span></th><th><span class="book-heading"><b class="venue-icon polymarket">◇</b>Polymarket US</span></th><th><span class="book-heading"><b class="venue-icon novig">N</b>Novig</span></th><th><span class="book-heading"><b class="venue-icon prophetx">P</b>ProphetX</span></th><th>Arbitrage</th></tr></thead><tbody>${records.map((record, index) => `<tr class="game-row" data-game-index="${index}" tabindex="0" role="link" aria-label="Open ${safe(record.kalshi_title || 'game')} market breakdown">
    <td><div class="game-teams">${teamsForRecord(record).map(teamMarkup).join('')}</div></td>
    <td><span class="start">${safe(startTime(record.start_time))}</span></td>
    <td><span class="label">Moneyline</span></td>
    <td>${pairForBook(record, record.kalshi_moneyline_asks, 'contract', 'yes_ask', record.kalshi_url, 'Kalshi')}</td>
    <td>${pairForBook(record, record.polymarket_us_displayed_moneyline_quotes, 'outcome', 'displayed_quote', record.polymarket_us_url, 'Polymarket US')}</td>
    <td class="unavailable-book" aria-label="Novig data not connected"></td>
    <td class="unavailable-book" aria-label="ProphetX data not connected"></td>
    <td>${arbitrageCell(record)}</td>
  </tr>`).join('')}</tbody></table>`;
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
  document.querySelector('#sport-title').textContent = 'Dashboard';
  document.querySelector('#sidebar-updated').textContent = `Updated ${new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(data.updated_at || Date.now()))}`;
  meta.textContent = 'Connected wallet balances · auto-refreshes every 30s';
  notice.textContent = 'Estimated edges use displayed quotes only. Verify executable prices, fees, and rules before acting.';
  const quotePair = quotes => `<div class="book-pair"><span class="price ${Number(quotes?.[0]) < .5 ? 'down' : 'up'}">${price(quotes?.[0])}</span><span class="price ${Number(quotes?.[1]) < .5 ? 'down' : 'up'}">${price(quotes?.[1])}</span></div>`;
  const opportunitiesTable = opportunities.length ? opportunities.map(row => `<tr><td>${row.teams?.length ? `<div class="game-teams">${row.teams.map(teamMarkup).join('')}</div>` : `<span class="game">${safe(row.title)}</span>`}</td><td><span class="start">${safe(startTime(row.start_time))}</span></td><td><span class="label">Moneyline</span></td><td>${quotePair(row.kalshi)}</td><td>${quotePair(row.polymarket_us)}</td><td class="unavailable-book"></td><td class="unavailable-book"></td><td>${row.edge ? `<div class="arb"><strong>+${(row.edge * 100).toFixed(2)}%</strong><small>Unverified</small></div>` : '<span class="no-arb">—</span>'}</td></tr>`).join('') : '<tr><td colspan="8" class="detail-empty">No current opportunities in cached reports. Select a sport and refresh its data.</td></tr>';
  const total = Object.values(sportCounts).reduce((sum, count) => sum + count, 0);
  const sportList = Object.entries(sportCounts).filter(([, count]) => count).sort((a, b) => b[1] - a[1]).map(([name, count]) => `<li><span>${safe(name)}</span><b>${count}</b></li>`).join('') || '<li><span>No report data yet</span></li>';
  tableWrap.innerHTML = `<section class="wallet-grid">${wallets.map(walletCard).join('')}</section><section class="opportunities"><div class="opportunity-heading"><div><h2>Top Opportunities</h2></div></div><div class="opportunity-table"><table><thead><tr><th>Game / Event</th><th>Start time</th><th>Market</th><th><span class="book-heading"><b class="venue-icon kalshi">K</b>Kalshi</span></th><th><span class="book-heading"><b class="venue-icon polymarket">◇</b>Polymarket US</span></th><th><span class="book-heading"><b class="venue-icon novig">N</b>Novig</span></th><th><span class="book-heading"><b class="venue-icon prophetx">P</b>ProphetX</span></th><th>Arbitrage</th></tr></thead><tbody>${opportunitiesTable}</tbody></table></div></section><section class="sport-summary"><div class="summary-ring"><strong>${total}</strong><span>Games</span></div><div><h2>Opportunities by sport</h2><ul>${sportList}</ul></div></section>`;
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

async function loadSport(refreshData = false) {
  const sport = activeSport;
  if (!sport || refreshingSports.has(sport)) return;
  refreshingSports.add(sport);
  refresh.disabled = true;
  refresh.textContent = refreshData ? 'Refreshing…' : 'Refresh data';
  try {
    const endpoint = `/api/sports/${sport}${refreshData ? '/refresh' : ''}`;
    const response = await fetch(endpoint, { method: refreshData ? 'POST' : 'GET' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Unable to load ${sport} data`);
    // Do not overwrite a newly selected tab with a slower previous request.
    if (activeSport === sport) renderSport(data);
  } catch (error) {
    if (activeSport === sport) {
      meta.textContent = `Could not load ${sport} data.`;
      tableWrap.innerHTML = `<div class="empty"><h2>Data unavailable</h2><p>${safe(error.message)}</p></div>`;
    }
  } finally {
    refreshingSports.delete(sport);
    if (activeSport === sport) {
      refresh.disabled = false;
      refresh.textContent = 'Refresh data';
    }
  }
}

tabs.forEach(tab => tab.addEventListener('click', () => {
  activeSport = tab.dataset.sport;
  tabs.forEach(item => item.classList.toggle('active', item === tab));
  home.classList.remove('active');
  refresh.hidden = false;
  loadSport();
}));
home.addEventListener('click', event => {
  event.preventDefault();
  activeSport = null;
  home.classList.add('active');
  tabs.forEach(item => item.classList.remove('active'));
  loadHome();
});
refresh.addEventListener('click', () => activeSport ? loadSport(true) : loadHome());
function openGameDetail(record) {
  const params = new URLSearchParams({
    sport: activeSport,
    kalshi: record.kalshi_event_ticker,
    polymarket: record.polymarket_us_event_slug,
  });
  window.location.assign(`/game.html?${params}`);
}
tableWrap.addEventListener('click', event => {
  const row = event.target.closest('.game-row');
  if (!row || event.target.closest('a')) return;
  openGameDetail(latestRecords[Number(row.dataset.gameIndex)]);
});
tableWrap.addEventListener('keydown', event => {
  if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('.game-row')) {
    event.preventDefault();
    openGameDetail(latestRecords[Number(event.target.dataset.gameIndex)]);
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
