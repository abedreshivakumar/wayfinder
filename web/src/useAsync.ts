import { useCallback, useState } from "react";

// Runs one async action and tracks whether it is running, what it returned, and how it failed.
export function useAsync<A extends unknown[], T>(fn: (...args: A) => Promise<T>) {
  const [state, set] = useState<{ loading: boolean; data: T | null; error: string | null }>({ loading: false, data: null, error: null });
  const run = useCallback(
    async (...args: A) => {
      set({ loading: true, data: null, error: null });
      try {
        const data = await fn(...args);
        set({ loading: false, data, error: null });
        return data;
      } catch (e) {
        set({ loading: false, data: null, error: e instanceof Error ? e.message : String(e) });
        return null;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  return { ...state, run };
}
