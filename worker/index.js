// greenflash-trigger: a Cloudflare Worker cron that fires the publish-brief
// workflow at the real scheduled minute.
//
// GitHub's own cron queue ran this repo hours late on every measured run
// (see ../README.md, "Why the odd minutes"), which pushed the 3pm evening
// call past sunset. Cloudflare cron triggers fire on time. This Worker is
// the clock; GitHub's six crons stay in publish.yml as a fallback.
//
// One cron trigger (the free plan allows five per account) fires at :07,
// :17 and :27 every hour. The Worker converts the fire time to Pacific and
// dispatches only on the three (hour, minute) pairs below -- so DST is a
// non-issue and each slot fires exactly once a day.

const REPO = "jmcraigmile/daily-surf-brief";
const WORKFLOW = "publish.yml";
// Pacific hour -> the minute that slot fires on. Same minutes as publish.yml.
const SLOTS = { 6: 7, 15: 17, 21: 27 }; // day-of, evening-only, night-before

function pacific(date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles", hour: "numeric", minute: "numeric", hour12: false,
  }).formatToParts(date);
  const get = (t) => Number(parts.find((p) => p.type === t).value);
  return { hour: get("hour") % 24, minute: get("minute") }; // "24" at midnight in some runtimes
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
    const { hour, minute } = pacific(new Date(event.scheduledTime));
    if (SLOTS[hour] !== minute) return; // 69 of 72 daily fires end here, silently
    const status = await dispatch(env);
    console.log(`dispatch ${WORKFLOW} at Pacific ${hour}:${String(minute).padStart(2, "0")}: HTTP ${status}`);
  },

  // The Worker has a URL; make it say something harmless instead of erroring.
  async fetch() {
    return new Response("greenflash-trigger: fires publish-brief at 6:07am, 3:17pm, 9:27pm Pacific\n",
      { headers: { "Content-Type": "text/plain" } });
  },
};
