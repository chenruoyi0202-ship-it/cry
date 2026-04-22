// Cloudflare Worker: Yahoo Finance proxy for 02680.HK
// Only allows requests to Yahoo Finance chart API for the specific stock
// Deploy: npx wrangler deploy

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: cors });
    }

    // Only allow GET
    if (request.method !== 'GET') {
      return new Response('Method not allowed', { status: 405, headers: cors });
    }

    // Parse params
    const symbol = url.searchParams.get('symbol') || '2680.HK';
    const interval = url.searchParams.get('interval') || '1d';
    const range = url.searchParams.get('range') || '6mo';

    // Whitelist: only allow known symbols and intervals
    const allowedSymbols = ['2680.HK'];
    const allowedIntervals = ['1m', '5m', '15m', '30m', '1d', '1wk', '1mo'];
    const allowedRanges = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y'];

    if (!allowedSymbols.includes(symbol)) {
      return new Response(JSON.stringify({ error: 'Symbol not allowed' }), {
        status: 403, headers: { ...cors, 'Content-Type': 'application/json' }
      });
    }
    if (!allowedIntervals.includes(interval) || !allowedRanges.includes(range)) {
      return new Response(JSON.stringify({ error: 'Invalid interval or range' }), {
        status: 400, headers: { ...cors, 'Content-Type': 'application/json' }
      });
    }

    const yahooUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?interval=${interval}&range=${range}`;

    try {
      const resp = await fetch(yahooUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
        cf: { cacheTtl: interval === '1d' ? 3600 : 60 }, // cache daily 1hr, intraday 1min
      });

      if (!resp.ok) {
        return new Response(JSON.stringify({ error: `Yahoo returned ${resp.status}` }), {
          status: resp.status, headers: { ...cors, 'Content-Type': 'application/json' }
        });
      }

      const data = await resp.text();
      return new Response(data, {
        headers: {
          ...cors,
          'Content-Type': 'application/json',
          'Cache-Control': interval === '1d' ? 'public, max-age=3600' : 'public, max-age=60',
        }
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 502, headers: { ...cors, 'Content-Type': 'application/json' }
      });
    }
  }
};
