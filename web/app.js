const tabs = [...document.querySelectorAll('.tab')];
const tableWrap = document.querySelector('#table-wrap');
const meta = document.querySelector('#meta');
const notice = document.querySelector('#notice');
const refresh = document.querySelector('#refresh');
let activeSport = 'football';
let latestRecords = [];

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
  meta.textContent = `${records.length} matched ${sportName.toLowerCase()} games${data.kalshi_events_compared ? ` · compared ${data.kalshi_events_compared} Kalshi and ${data.polymarket_events_compared} Polymarket US events` : ''}`;
  notice.textContent = data.quote_notice;
  if (!records.length) { tableWrap.innerHTML = `<div class="empty"><h2>No matched ${safe(sportName.toLowerCase())} games</h2><p>There are no likely open cross-venue matches in the latest public feeds. Refresh to check again.</p></div>`; return; }
  tableWrap.innerHTML = `<table><colgroup><col class="game-column"><col class="time-column"><col class="market-column"><col class="book-column"><col class="book-column"><col class="book-column"><col class="book-column"><col class="arbitrage-column"></colgroup><thead><tr><th>Game / Event</th><th>Start time</th><th>Market</th><th><span class="book-heading"><b class="venue-icon kalshi">K</b>Kalshi</span></th><th><span class="book-heading"><b class="venue-icon polymarket">◇</b>Polymarket US</span></th><th><span class="book-heading"><b class="venue-icon novig">N</b>Novig</span></th><th><span class="book-heading"><b class="venue-icon prophetx">P</b>ProphetX</span></th><th>Arbitrage</th></tr></thead><tbody>${records.map(record => `<tr>
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

async function loadSport(refreshData = false) {
  refresh.disabled = true;
  refresh.textContent = refreshData ? 'Refreshing…' : 'Refresh data';
  try {
    const endpoint = `/api/sports/${activeSport}${refreshData ? '/refresh' : ''}`;
    const response = await fetch(endpoint, { method: refreshData ? 'POST' : 'GET' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Unable to load ${activeSport} data`);
    renderSport(data);
  } catch (error) {
    meta.textContent = `Could not load ${activeSport} data.`;
    tableWrap.innerHTML = `<div class="empty"><h2>Data unavailable</h2><p>${safe(error.message)}</p></div>`;
  } finally { refresh.disabled = false; refresh.textContent = 'Refresh data'; }
}

tabs.forEach(tab => tab.addEventListener('click', () => {
  activeSport = tab.dataset.sport;
  tabs.forEach(item => item.classList.toggle('active', item === tab));
  refresh.hidden = false;
  loadSport();
}));
refresh.addEventListener('click', () => loadSport(true));
document.querySelector('#search').addEventListener('input', event => {
  const query = event.target.value.trim().toLowerCase();
  document.querySelectorAll('#table-wrap tbody tr').forEach((row, index) => {
    const record = latestRecords[index];
    row.hidden = Boolean(query) && !JSON.stringify(record).toLowerCase().includes(query);
  });
});
setInterval(() => { document.querySelector('#clock').textContent = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' }).format(new Date()); }, 1000);
loadSport();
