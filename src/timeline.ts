export const SECONDS_PER_DAY = 24 * 60 * 60;
export const DAYS_PER_YEAR = 365;
export const SIMULATION_DURATION_DAYS = 60;
export const DEFAULT_DURATION_SECONDS = SIMULATION_DURATION_DAYS * SECONDS_PER_DAY;

export function clampTimelineTime(seconds: number, durationSeconds: number) {
  if (!Number.isFinite(seconds) || !Number.isFinite(durationSeconds) || durationSeconds <= 0) return 0;
  return Math.min(durationSeconds, Math.max(0, seconds));
}

export function placementTime(seconds: number, durationSeconds: number) {
  return Math.round(clampTimelineTime(seconds, durationSeconds));
}

export function formatTime(seconds: number) {
  const wholeSeconds = Math.floor(Math.max(0, Number.isFinite(seconds) ? seconds : 0));
  const totalDays = Math.floor(wholeSeconds / SECONDS_PER_DAY);
  const years = Math.floor(totalDays / DAYS_PER_YEAR);
  const days = totalDays % DAYS_PER_YEAR;
  const hours = Math.floor((wholeSeconds % SECONDS_PER_DAY) / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  const dayAndTime = `${days}d ${hours.toString().padStart(2, "0")}h ${minutes.toString().padStart(2, "0")}m`;
  return years > 0 ? `${years}y ${dayAndTime}` : dayAndTime;
}

export function formatDurationLabel(seconds: number) {
  const days = Math.round(Math.max(0, seconds) / SECONDS_PER_DAY);
  if (days % DAYS_PER_YEAR === 0 && days >= DAYS_PER_YEAR) {
    const years = days / DAYS_PER_YEAR;
    return `${years} ${years === 1 ? "year" : "years"}`;
  }
  return `${days} ${days === 1 ? "day" : "days"}`;
}

export function audioTimeToTimeline(audioTime: number, audioDuration: number, durationSeconds: number) {
  if (!Number.isFinite(audioDuration) || audioDuration <= 0) return 0;
  return clampTimelineTime((audioTime / audioDuration) * durationSeconds, durationSeconds);
}

export function timelineTimeToAudio(seconds: number, durationSeconds: number, audioDuration: number) {
  if (!Number.isFinite(audioDuration) || audioDuration <= 0 || durationSeconds <= 0) return 0;
  return (clampTimelineTime(seconds, durationSeconds) / durationSeconds) * audioDuration;
}
