'use client';

import { Navigation } from '@/components/layout/navigation';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useState } from 'react';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { useDeveloperMode } from '@/lib/developer-mode';
import { useDatabase } from '@/lib/database-context';
import config from '@/lib/config';
export default function SettingsPage() {
  const { selectedDb, setSelectedDb, availableDatabases } = useDatabase();
  const { isEnabled: devModeEnabled, setEnabled: setDevModeEnabled } = useDeveloperMode();

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main className="container mx-auto px-4 py-8">
        <div className="space-y-6">
          <div>
            <h1 className="text-3xl font-bold">Settings</h1>
            <p className="text-muted-foreground">
              Configuration and preferences
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>API Configuration</CardTitle>
                <CardDescription>
                  Backend API connection settings
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label>API Base URL</Label>
                  <div className="mt-2">
                    <Badge variant="outline" className="font-mono">
                      {config.api.baseUrl}
                    </Badge>
                  </div>
                </div>

                <div>
                  <Label>API Version</Label>
                  <div className="mt-2">
                    <Badge variant="secondary">
                      {config.app.version}
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Database Selection</CardTitle>
                <CardDescription>
                  Choose which seeded database to use
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <Label htmlFor="database-select">Current Database</Label>
                  <Select value={selectedDb} onValueChange={setSelectedDb}>
                    <SelectTrigger id="database-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availableDatabases.map((db) => (
                        <SelectItem key={db.value} value={db.value}>
                          {db.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-sm text-muted-foreground">
                    Selected database will be used across all views
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card className="md:col-span-2">
              <CardHeader>
                <CardTitle>Developer Mode</CardTitle>
                <CardDescription>
                  Enable advanced developer features including SQL console
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center space-x-2">
                  <Switch
                    id="dev-mode"
                    checked={devModeEnabled}
                    onCheckedChange={setDevModeEnabled}
                  />
                  <Label htmlFor="dev-mode">Enable Developer Mode</Label>
                </div>
                {devModeEnabled && (
                  <div className="mt-4 p-4 bg-muted rounded-lg">
                    <p className="text-sm text-muted-foreground">
                      Developer mode is enabled. You can now access the SQL console in the Ledger tab.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
