'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
// import { cn } from '@/lib/utils';
// import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ThemeToggle } from './theme-toggle';
import config from '@/lib/config';

const navigationItems = [
  { href: '/identity', label: 'Identity' },
  { href: '/ledger', label: 'Ledger' },
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/visualize', label: 'Visualize' },
  { href: '/traces', label: 'Traces' },
  { href: '/settings', label: 'Settings' },
];

export function Navigation() {
  const pathname = usePathname();
  
  // Determine active tab based on pathname
  const activeTab = pathname === '/' ? '/dashboard' : pathname;

  return (
    <header className="border-b">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-6">
            <Link href="/" className="text-xl font-bold">
              {config.app.name}
            </Link>
            
            <Tabs value={activeTab} className="w-auto">
              <TabsList className="grid w-full grid-cols-6">
                {navigationItems.map((item) => (
                  <TabsTrigger key={item.href} value={item.href} asChild>
                    <Link href={item.href}>
                      {item.label}
                    </Link>
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>
          
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
