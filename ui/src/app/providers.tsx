'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { ThemeProvider } from 'next-themes';
import { useState } from 'react';
import { DeveloperModeProvider } from '@/lib/developer-mode';
import { DatabaseProvider } from '@/lib/database-context';

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 1 minute
            retry: 1,
          },
        },
      }
    )
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        disableTransitionOnChange
      >
        <DeveloperModeProvider>
          <DatabaseProvider>
            {children}
            <ReactQueryDevtools initialIsOpen={false} />
          </DatabaseProvider>
        </DeveloperModeProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
