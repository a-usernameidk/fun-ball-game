// One global Durable Object that caps how many cloud-physics rooms run at once.
// Rooms take a lease when they start simulating and renew it every minute;
// a lease that isn't renewed for 2 minutes expires (e.g. if a room crashed).

const LEASE_MS = 120000;

export class Limiter {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const room = (url.searchParams.get("room") || "").slice(0, 16);
    const max = Math.max(1, parseInt(url.searchParams.get("max"), 10) || 5);
    const now = Date.now();
    const leases = (await this.state.storage.get("leases")) || {};
    for (const [k, exp] of Object.entries(leases)) if (exp < now) delete leases[k];

    let ok = true;
    switch (url.pathname) {
      case "/acquire":
        if (!leases[room] && Object.keys(leases).length >= max) ok = false;
        else leases[room] = now + LEASE_MS;
        break;
      case "/renew":
        if (leases[room]) leases[room] = now + LEASE_MS;
        else ok = false;
        break;
      case "/release":
        delete leases[room];
        break;
      default:
        return new Response("not found", { status: 404 });
    }
    await this.state.storage.put("leases", leases);
    return Response.json({ ok, active: Object.keys(leases).length, max });
  }
}
