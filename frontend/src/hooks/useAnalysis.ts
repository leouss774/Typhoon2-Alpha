import { useState, useEffect, useCallback } from "react";
import type { DashboardData } from "../types/models";
import { api } from "../services/api";

interface UseAnalysisReturn {
  data: DashboardData | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useAnalysis(sessionId: string): UseAnalysisReturn {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getDashboard(sessionId);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refresh: fetchData };
}
