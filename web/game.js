const detail = document.querySelector('#game-detail');
const query = new URLSearchParams(location.search);
const sport = query.get('sport');
const kalshiTicker = query.get('kalshi');
const polymarketSlug = query.get('polymarket');
const leagues = query.get('leagues');
const offset = query.get('offset') || '0';
const safe = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const price = value => value == null ? '—' : `$${Number(value).toFixed(3)}`;
const startTime = value => value ? new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value)) : 'Time unavailable';

function venueCard(name, iconClass, icon, url, headings, rows) {
  const body = rows.length ? `<table><thead><tr>${headings.map(heading => `<th>${safe(heading)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(value => `<td>${value}</td>`).join('')}</tr>`).join('')}</tbody></table>` : '<p class="detail-empty">No current market quotes were returned.</p>';
  return `<section class="venue-detail"><header><b class="venue-icon ${iconClass}">${icon}</b><strong>${name}</strong>${url ? `<a href="${safe(url)}" target="_blank" rel="noopener noreferrer">Open venue ↗</a>` : ''}</header>${body}</section>`;
}

const categories = [
  ['moneyline', 'Two-way moneylines', 'Winner markets only; soccer three-way markets remain review-only.'],
  ['spread', 'Spreads', 'Compare the exact line, push rules, game period, and overtime treatment.'],
  ['total', 'Totals', 'Compare the exact total, over/under direction, and settlement scope.'],
  ['props', 'Player & live props', 'Shown when supplied by a venue. They are not automatically matched across venues.'],
];

function categorySection(record, category, title, note) {
  const fallbackKalshi = category === 'moneyline' ? (record.kalshi_moneyline_asks || []).map(market => ({ ...market, market: market.contract })) : [];
  const fallbackPolymarket = category === 'moneyline' ? (record.polymarket_us_displayed_moneyline_quotes || []).map(quote => ({ ...quote, market: 'Moneyline' })) : [];
  let kalshi = (record.kalshi_market_breakdown || fallbackKalshi).filter(market => market.category === category || (!market.category && category === 'moneyline'));
  let polymarket = (record.polymarket_us_market_breakdown || fallbackPolymarket).filter(market => market.category === category || (!market.category && category === 'moneyline'));
  // Reports created before category support still have valid moneyline quotes.
  if (category === 'moneyline' && !kalshi.length) kalshi = fallbackKalshi;
  if (category === 'moneyline' && !polymarket.length) polymarket = fallbackPolymarket;
  const kalshiRows = kalshi.map(market => [safe(market.market || 'Market'), `<span class="price">${price(market.yes_ask)}</span>`, `<span class="price">${price(market.no_ask)}</span>`]);
  const polymarketRows = polymarket.map(market => [safe(`${market.market || 'Market'} · ${market.outcome || 'Outcome'}`), `<span class="price">${price(market.displayed_quote)}</span>`]);
  return `<section class="detail-market-section"><div><h2>${title}</h2><p>${note}</p></div><div class="game-detail-grid">${venueCard('Kalshi', 'kalshi', 'K', record.kalshi_url, ['Contract', 'YES ask', 'NO ask'], kalshiRows)}${venueCard('Polymarket US', 'polymarket', '◇', record.polymarket_us_url, ['Market / outcome', 'Displayed quote'], polymarketRows)}</div></section>`;
}

function render(record) {
  const title = record.polymarket_us_title || record.kalshi_title || 'Game breakdown';
  detail.innerHTML = `<div class="game-detail-header"><div><p class="eyebrow">${safe(sport || 'SPORT').toUpperCase()} · MARKET BREAKDOWN</p><h1>${safe(title)}</h1><p class="meta">Starts ${safe(startTime(record.start_time))}</p></div></div>${categories.map(category => categorySection(record, ...category)).join('')}<p class="detail-note">Quotes are for research. Confirm current executable prices, fees, market scope, and settlement rules on each venue before acting.</p>`;
}

async function load() {
  if (!sport || !kalshiTicker || !polymarketSlug) throw new Error('This game link is incomplete. Return to the market board and select the game again.');
  const requestQuery = new URLSearchParams({ offset, limit: '25' });
  if (leagues) requestQuery.set('leagues', leagues);
  const response = await fetch(`/api/sports/${encodeURIComponent(sport)}?${requestQuery}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Unable to load this game.');
  const record = (data.records || []).find(item => item.kalshi_event_ticker === kalshiTicker && item.polymarket_us_event_slug === polymarketSlug);
  if (!record) throw new Error('This game is no longer active or is unavailable in the latest report.');
  render(record);
}

load().catch(error => { detail.innerHTML = `<div class="empty"><h2>Game unavailable</h2><p>${safe(error.message)}</p></div>`; });
setInterval(() => { document.querySelector('#clock').textContent = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' }).format(new Date()); }, 1000);
