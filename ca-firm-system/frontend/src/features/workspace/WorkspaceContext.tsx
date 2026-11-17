import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { getClient, listClients, listPeriods } from '../../services/clientsApi';
import type { Client, Period } from '../../types/clients';

interface WorkspaceContextType {
  activeClient: Client | null;
  activePeriod: Period | null;
  clientsList: Client[];
  periodsList: Period[];
  loading: boolean;
  setActiveWorkspace: (client: Client, period: Period) => void;
  setActiveClientById: (clientId: string) => Promise<void>;
  setActivePeriodById: (periodId: string) => void;
  syncFromParams: (clientId?: string, periodId?: string) => Promise<void>;
  refreshWorkspace: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextType | null>(null);

const STORAGE_CLIENT_KEY = 'finora_active_client_id';
const STORAGE_PERIOD_KEY = 'finora_active_period_id';

export const WorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeClient, setActiveClient] = useState<Client | null>(null);
  const [activePeriod, setActivePeriod] = useState<Period | null>(null);
  const [clientsList, setClientsList] = useState<Client[]>([]);
  const [periodsList, setPeriodsList] = useState<Period[]>([]);
  const [loading, setLoading] = useState(false);

  // Load clients list on mount
  useEffect(() => {
    let mounted = true;
    async function init() {
      try {
        const res = await listClients({ limit: 50 });
        if (mounted && res.items.length > 0) {
          setClientsList(res.items);
          const savedClientId = localStorage.getItem(STORAGE_CLIENT_KEY);
          const defaultClient = res.items.find((c) => c.id === savedClientId) || res.items[0];
          setActiveClient(defaultClient);

          const pers = await listPeriods(defaultClient.id);
          if (mounted) {
            setPeriodsList(pers);
            const savedPeriodId = localStorage.getItem(STORAGE_PERIOD_KEY);
            const defaultPeriod = pers.find((p) => p.id === savedPeriodId) || pers[0] || null;
            setActivePeriod(defaultPeriod);
          }
        }
      } catch {
        // Non-blocking initialization
      }
    }
    void init();
    return () => {
      mounted = false;
    };
  }, []);

  const setActiveWorkspace = useCallback((client: Client, period: Period) => {
    setActiveClient(client);
    setActivePeriod(period);
    localStorage.setItem(STORAGE_CLIENT_KEY, client.id);
    localStorage.setItem(STORAGE_PERIOD_KEY, period.id);
  }, []);

  const setActiveClientById = useCallback(
    async (clientId: string) => {
      try {
        setLoading(true);
        const client = await getClient(clientId);
        setActiveClient(client);
        localStorage.setItem(STORAGE_CLIENT_KEY, client.id);

        const pers = await listPeriods(client.id);
        setPeriodsList(pers);
        if (pers.length > 0) {
          setActivePeriod(pers[0]);
          localStorage.setItem(STORAGE_PERIOD_KEY, pers[0].id);
        } else {
          setActivePeriod(null);
          localStorage.removeItem(STORAGE_PERIOD_KEY);
        }
      } catch (err) {
        console.error('Failed to set active client', err);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const setActivePeriodById = useCallback(
    (periodId: string) => {
      const match = periodsList.find((p) => p.id === periodId);
      if (match) {
        setActivePeriod(match);
        localStorage.setItem(STORAGE_PERIOD_KEY, match.id);
      }
    },
    [periodsList]
  );

  const syncFromParams = useCallback(
    async (clientId?: string, periodId?: string) => {
      if (!clientId) return;
      if (activeClient?.id !== clientId) {
        try {
          const client = await getClient(clientId);
          setActiveClient(client);
          localStorage.setItem(STORAGE_CLIENT_KEY, client.id);

          const pers = await listPeriods(client.id);
          setPeriodsList(pers);

          if (periodId) {
            const p = pers.find((x) => x.id === periodId);
            if (p) {
              setActivePeriod(p);
              localStorage.setItem(STORAGE_PERIOD_KEY, p.id);
            }
          } else if (pers.length > 0) {
            setActivePeriod(pers[0]);
          }
        } catch {
          // Ignore sync failure
        }
      } else if (periodId && activePeriod?.id !== periodId) {
        const p = periodsList.find((x) => x.id === periodId);
        if (p) {
          setActivePeriod(p);
          localStorage.setItem(STORAGE_PERIOD_KEY, p.id);
        }
      }
    },
    [activeClient, activePeriod, periodsList]
  );

  const refreshWorkspace = useCallback(async () => {
    try {
      const res = await listClients({ limit: 50 });
      setClientsList(res.items);
      if (activeClient) {
        const pers = await listPeriods(activeClient.id);
        setPeriodsList(pers);
      }
    } catch {
      // Non-blocking
    }
  }, [activeClient]);

  return (
    <WorkspaceContext.Provider
      value={{
        activeClient,
        activePeriod,
        clientsList,
        periodsList,
        loading,
        setActiveWorkspace,
        setActiveClientById,
        setActivePeriodById,
        syncFromParams,
        refreshWorkspace,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
};

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used within WorkspaceProvider');
  }
  return ctx;
}
