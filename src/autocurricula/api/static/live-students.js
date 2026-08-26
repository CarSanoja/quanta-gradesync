function lowestConfidence(criteria) {
  const values = (Array.isArray(criteria) ? criteria : [])
    .map((criterion) => Number(criterion && criterion.confidence))
    .filter((value) => Number.isFinite(value));
  return values.length ? Math.min(...values) : null;
}

function percentageOf(student) {
  const value = Number(student.percentage);
  return Number.isFinite(value) ? value : null;
}

export function createStudentLoader({ state, guard, getJson, endpoints, onLoaded }) {
  return async function loadStudents() {
    const jobId = state.activeJobId;
    if (!jobId || state.jobDetailId === jobId) {
      return;
    }
    state.jobDetailId = jobId;
    const detail = await guard(() => getJson(endpoints.job(jobId)));
    if (!detail) {
      if (state.jobDetailId === jobId) {
        state.jobDetailId = null;
      }
      return;
    }
    if (state.activeJobId !== jobId) {
      return;
    }
    state.students = studentSummaries(detail);
    onLoaded();
  };
}

export function studentSummaries(detail) {
  const summaries = new Map();
  const students = detail && Array.isArray(detail.students) ? detail.students : [];
  students.forEach((student) => {
    if (!student || !student.student_id) {
      return;
    }
    summaries.set(student.student_id, {
      percentage: percentageOf(student),
      lowestConfidence: lowestConfidence(student.criteria),
      sisStatus: String(student.sis_status || ""),
    });
  });
  return summaries;
}
