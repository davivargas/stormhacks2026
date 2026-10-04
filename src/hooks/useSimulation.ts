import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, simulate } from "../lib/api";
import type { SimulationRequest, SimulationResponse } from "../types";

export function useSimulation() {
  const [run, setRun] = useState<SimulationResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "dirty" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<ApiError | null>(null);
  const version = useRef(0);
  const pending = useRef<AbortController | null>(null);

  const invalidate = useCallback((clearRun = false) => {
    version.current += 1;
    pending.current?.abort();
    pending.current = null;
    setError(null);
    setStatus(clearRun ? "idle" : "dirty");
    if (clearRun) setRun(null);
  }, []);

  const calculate = useCallback(async (body: SimulationRequest) => {
    if (pending.current) return null;
    const controller = new AbortController();
    pending.current = controller;
    const requestVersion = ++version.current;
    setStatus("loading");
    setError(null);

    try {
      const result = await simulate(body, controller.signal);
      if (requestVersion !== version.current || controller.signal.aborted) return null;
      setRun(result);
      setStatus("ready");
      return result;
    } catch (failure) {
      if (requestVersion !== version.current || controller.signal.aborted) return null;
      setError(failure instanceof ApiError ? failure : new ApiError("Could not calculate paths. Please retry.", "request_failed"));
      setStatus("error");
      return null;
    } finally {
      if (pending.current === controller) pending.current = null;
    }
  }, []);

  useEffect(() => () => {
    version.current += 1;
    pending.current?.abort();
  }, []);

  return { run, status, error, calculate, invalidate };
}
