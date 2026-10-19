// One global Durable Object that balances cloud physics across everyone.
//
// It tracks which cloud rooms are running right now (leases) and how much cloud time
// has been used today, so rooms can share the "power" fairly: one room alone gets the
// most, many rooms split it, and a heavy day turns everything down gently instead of
// running out of Cloudflare's free daily allowance.
//
// Rooms renew their lease every few seconds; a lease that isn't renewed for 2 minutes
// expires (e.g. if a room crashed).

const LEASE_MS = 120000;

function today() {
  return new Date().toISOString().slice(0, 10); // UTC date, resets at midnight UTC
}

export class Limiter {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const room = (url.searchParams.get("room") || "").slice(0, 16);
    const max = Math.max(1, parseInt(url.searchParams.get("max"), 10) || 5);
    const budget = Math.max(0, parseFloat(url.searchParams.get("budget")) || 0); // seconds per day, 0 = no limit
    const add = Math.min(60, Math.max(0, parseFloat(url.searchParams.get("add")) || 0));
    const now = Date.now();
    const st = (await this.state.storage.get("state")) || { leases: {}, day: today(), used: 0 };
    if (st.day !== today()) { st.day = today(); st.used = 0; }
    for (const [k, exp] of Object.entries(st.leases)) if (exp < now) delete st.leases[k];

    let ok = true, reason = "";
    switch (url.pathname) {
      case "/acquire":
        if (budget && st.used >= budget) { ok = false; reason = "tired"; }
        else if (!st.leases[room] && Object.keys(st.leases).length >= max) { ok = false; reason = "busy"; }
        else st.leases[room] = now + LEASE_MS;
        break;
      case "/renew":
        if (st.leases[room]) { st.leases[room] = now + LEASE_MS; st.used += add; }
        else ok = false;
        break;
      case "/release":
        st.used += add;
        delete st.leases[room];
        break;
      default:
        return new Response("not found", { status: 404 });
    }
    await this.state.storage.put("state", st);
    return Response.json({ ok, reason, active: Object.keys(st.leases).length, max, used: st.used, budget });
  }
}
