'use client';

import { createContext, useContext, useState, useEffect } from 'react';

interface DeveloperModeContextType {
  isEnabled: boolean;
  setEnabled: (enabled: boolean) => void;
}

const DeveloperModeContext = createContext<DeveloperModeContextType | undefined>(undefined);

export function DeveloperModeProvider({ children }: { children: React.ReactNode }) {
  const [isEnabled, setEnabled] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem('pmm-dev-mode');
    if (stored === 'true') {
      setEnabled(true);
    }
  }, []);

  // Save to localStorage when changed
  useEffect(() => {
    localStorage.setItem('pmm-dev-mode', isEnabled.toString());
  }, [isEnabled]);

  return (
    <DeveloperModeContext.Provider value={{ isEnabled, setEnabled }}>
      {children}
    </DeveloperModeContext.Provider>
  );
}

export function useDeveloperMode() {
  const context = useContext(DeveloperModeContext);
  if (context === undefined) {
    throw new Error('useDeveloperMode must be used within a DeveloperModeProvider');
  }
  return context;
}
