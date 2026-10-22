// greenflash-trigger: a Cloudflare Worker cron that fires the publish-brief
// workflow at the real scheduled minute.
//
// GitHub's own cron queue ran this repo hours late on every measured run
// (see ../README.md, "Why the odd minutes"), which pushed the 3pm evening
// call past sunset. Cloudflare cron triggers fire on time. This Worker is
// the clock; GitHub's six crons stay in publish.yml as a fallback.
//
// The six UTC crons below are the same minutes as publish.yml, one for each
// DST offset. Only the one that lands on the intended Pacific hour actually
// dispatches, so the workflow runs three times a day, not six.

const REPO = "jmcraigmile/daily-surf-brief";
const WORKFLOW = "publish.yml";
const PACIFIC_HOURS = new Set([6, 15, 21]); // day-of, evening-only, night-before

function pacificHour(date) {
  const h = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles", hour: "numeric", hour12: false,
  }).format(date);
  return Number(h) % 24; // Intl yields "24" at midnight in some runtimes
}

async function dispatch(env) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "greenflash-trigger",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main" }),
    },
  );
  // 204 is the only success; anything else is worth seeing in the Worker logs
  return res.status;
}

export default {
  async scheduled(event, env, ctx) {
    const now = new Date(event.scheduledTime);
    const hour = pacificHour(now);
    if (!PACIFIC_HOURS.has(hour)) {
      console.log(`skip: cron "${event.cron}" is the off-DST twin (Pacific hour ${hour})`);
      return;
    }
    const status = await dispatch(env);
    console.log(`dispatch ${WORKFLOW} for Pacific hour ${hour}: HTTP ${status}`);
  },

  // The Worker has a URL; make it say something harmless instead of erroring.
  async fetch() {
    return new Response("greenflash-trigger: fires publish-brief at 6:07am, 3:17pm, 9:27pm Pacific\n",
      { headers: { "Content-Type": "text/plain" } });
  },
};
