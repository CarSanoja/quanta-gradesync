import { isTerminal, jobsSignature } from "/console/assets/live-focus.js";

const POLL_MS = 2500;
const IDLE_POLLS_BEFORE_REST = 4;

export function createJobsPoller({ load, jobsOf, indicator }) {
  let timer = null;
  let signature = "";
  let idlePolls = 0;

  function running(jobs) {
    return (jobs || []).some((job) => !isTerminal(job.stage));
  }

  function stop() {
    if (timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
    indicator(false);
  }

  async function tick() {
    await load();
    const jobs = jobsOf();
    const next = jobsSignature(jobs);
    idlePolls = next === signature ? idlePolls + 1 : 0;
    signature = next;
    if (running(jobs)) {
      idlePolls = 0;
      return;
    }
    if (idlePolls >= IDLE_POLLS_BEFORE_REST) {
      stop();
    }
  }

  function start() {
    stop();
    signature = jobsSignature(jobsOf());
    idlePolls = 0;
    indicator(true);
    timer = window.setInterval(tick, POLL_MS);
  }

  return { start, stop };
}
