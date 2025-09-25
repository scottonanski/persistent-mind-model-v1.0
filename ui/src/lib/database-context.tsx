'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { databases, defaultDatabase } from './databases';

interface DatabaseContextType {
  selectedDb: string;
  setSelectedDb: (db: string) => void;
  availableDatabases: typeof databases;
}

const DatabaseContext = createContext<DatabaseContextType | undefined>(undefined);

export function DatabaseProvider({ children }: { children: ReactNode }) {
  const [selectedDb, setSelectedDbState] = useState(defaultDatabase);

  // Load from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem('pmm-selected-database');
    if (stored && databases.some(db => db.value === stored)) {
      setSelectedDbState(stored);
    }
  }, []);

  // Save to localStorage when changed
  const setSelectedDb = (db: string) => {
    setSelectedDbState(db);
    localStorage.setItem('pmm-selected-database', db);
  };

  return (
    <DatabaseContext.Provider value={{ 
      selectedDb, 
      setSelectedDb, 
      availableDatabases: databases 
    }}>
      {children}
    </DatabaseContext.Provider>
  );
}

export function useDatabase() {
  const context = useContext(DatabaseContext);
  if (context === undefined) {
    throw new Error('useDatabase must be used within a DatabaseProvider');
  }
  return context;
}
