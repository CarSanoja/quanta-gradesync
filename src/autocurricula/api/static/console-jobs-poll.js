import { isTerminal, jobsSignature } from "/console/assets/live-focus.js";

const ACTIVE_MS = 2500;
const IDLE_MS = 15000;
const IDLE_POLLS_BEFORE_RESTING = 4;

export function createJobsPoller({ load, jobsOf, indicator }) {
  let timer = null;
  let signature = "";
  let idlePolls = 0;
  let period = 0;

  function running(jobs) {
    return (jobs || []).some((job) => !isTerminal(job.stage));
  }

  function clear() {
    if (timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  function stop() {
    clear();
    period = 0;
    indicator(false);
  }

  function arm(next) {
    if (period === next) {
      return;
    }
    clear();
    period = next;
    timer = window.setInterval(tick, period);
  }

  async function tick() {
    await load();
    const jobs = jobsOf();
    const next = jobsSignature(jobs);
    idlePolls = next === signature ? idlePolls + 1 : 0;
    signature = next;
    if (running(jobs)) {
      idlePolls = 0;
      indicator(true);
      arm(ACTIVE_MS);
      return;
    }
    // Resting slows down; it never stops. A console that gives up when the
    // board is empty cannot notice the batch that arrives a minute later —
    // which is exactly the state a fresh database leaves it in.
    if (idlePolls >= IDLE_POLLS_BEFORE_RESTING) {
      indicator(false);
      arm(IDLE_MS);
    }
  }

  function start() {
    clear();
    signature = jobsSignature(jobsOf());
    idlePolls = 0;
    indicator(true);
    period = 0;
    arm(ACTIVE_MS);
  }

  return { start, stop };
}
