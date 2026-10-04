export const SECONDS_PER_DAY = 24 * 60 * 60;
export const SIMULATION_DURATION_DAYS = 10;
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
  const days = Math.floor(wholeSeconds / SECONDS_PER_DAY);
  const hours = Math.floor((wholeSeconds % SECONDS_PER_DAY) / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  return `${days}d ${hours.toString().padStart(2, "0")}h ${minutes.toString().padStart(2, "0")}m`;
}

export function audioTimeToTimeline(audioTime: number, audioDuration: number, durationSeconds: number) {
  if (!Number.isFinite(audioDuration) || audioDuration <= 0) return 0;
  return clampTimelineTime((audioTime / audioDuration) * durationSeconds, durationSeconds);
}

export function timelineTimeToAudio(seconds: number, durationSeconds: number, audioDuration: number) {
  if (!Number.isFinite(audioDuration) || audioDuration <= 0 || durationSeconds <= 0) return 0;
  return (clampTimelineTime(seconds, durationSeconds) / durationSeconds) * audioDuration;
}
