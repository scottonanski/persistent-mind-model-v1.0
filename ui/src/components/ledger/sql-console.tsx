'use client';

import { useState } from 'react';
import { ChangeEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { JsonView } from 'react-json-view-lite';
import { Play, Clock, Database, Eye, AlertCircle, CheckCircle } from 'lucide-react';
import { apiClient, SQLQueryResponse } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';

export function SQLConsole() {
  const { selectedDb } = useDatabase();
  const [query, setQuery] = useState(`SELECT id, kind, ts, content
FROM events
WHERE kind = 'reflection'
ORDER BY id DESC
LIMIT 10;`);
  const [isExecuting, setIsExecuting] = useState(false);
  const [queryResult, setQueryResult] = useState<SQLQueryResponse | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);

  const executeQuery = async () => {
    if (!query.trim()) return;

    setIsExecuting(true);
    setQueryError(null);
    setQueryResult(null);
    
    try {
      const result = await apiClient.executeSQL(selectedDb, query);
      console.log('SQL Query Result:', result);
      setQueryResult(result);
    } catch (error) {
      console.error('SQL Query Error:', error);
      setQueryError(error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Database className="h-4 w-4" />
          SQL Console
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label className="text-sm font-medium mb-2 block">SQL Query</label>
          <Textarea
            value={query}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setQuery(e.target.value)}
            placeholder="Enter SQL query..."
            className="font-mono text-sm"
            rows={8}
          />
        </div>

        <div className="flex items-center gap-4">
          <Button
            onClick={executeQuery}
            disabled={isExecuting || !query.trim()}
            className="flex items-center gap-2"
          >
            <Play className="h-4 w-4" />
            {isExecuting ? 'Executing...' : 'Execute Query'}
          </Button>

          <div className="text-sm text-muted-foreground flex items-center gap-1">
            <Database className="h-3 w-3" />
            Database: {selectedDb}
          </div>
        </div>

        <div className="text-xs text-muted-foreground">
          <p><strong>Allowed:</strong> SELECT queries only</p>
          <p><strong>Blocked:</strong> DROP, DELETE, INSERT, UPDATE, ALTER, CREATE, TRUNCATE</p>
          <p><strong>Tables:</strong> events (with columns: id, kind, ts, content, meta, hash, prev_hash)</p>
        </div>

        {/* Query Results */}
        {queryError && (
          <Card className="border-destructive">
            <CardContent className="pt-4">
              <div className="flex items-center gap-2 text-destructive">
                <AlertCircle className="h-4 w-4" />
                <span className="font-medium">Query Error</span>
              </div>
              <p className="text-sm mt-2">{queryError}</p>
            </CardContent>
          </Card>
        )}

        {queryResult && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                Query Results
              </CardTitle>
              <div className="flex gap-4 text-sm text-muted-foreground">
                <span>{queryResult.count} rows</span>
                <span>{queryResult.execution_time_ms}ms</span>
              </div>
            </CardHeader>
            <CardContent>
              {queryResult.results.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">No results found</p>
              ) : (
                <ScrollArea className="h-96 w-full">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {queryResult.results.length > 0 && Object.keys(queryResult.results[0] as Record<string, unknown>).map((column) => (
                          <TableHead key={column} className="font-medium">
                            {column}
                          </TableHead>
                        ))}
                        <TableHead className="w-12"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {queryResult.results.map((row, index) => (
                        <TableRow key={index}>
                          {Object.entries(row as Record<string, unknown>).map(([column, value]) => (
                            <TableCell key={column} className="font-mono text-sm">
                              {typeof value === 'object' && value !== null ? (
                                <Sheet>
                                  <SheetTrigger asChild>
                                    <Button variant="ghost" size="sm" className="h-6 px-2 text-xs">
                                      View JSON
                                    </Button>
                                  </SheetTrigger>
                                  <SheetContent side="right" className="max-w-2xl">
                                    <SheetHeader>
                                      <SheetTitle>JSON Data - {column}</SheetTitle>
                                      <SheetDescription>Row {index + 1}</SheetDescription>
                                    </SheetHeader>
                                    <div className="mt-4 max-h-[80vh] overflow-auto">
                                      <JsonView data={value} shouldExpandNode={() => false} />
                                    </div>
                                  </SheetContent>
                                </Sheet>
                              ) : (
                                <span className={value === null ? 'text-muted-foreground' : ''}>
                                  {value === null ? 'NULL' : String(value)}
                                </span>
                              )}
                            </TableCell>
                          ))}
                          <TableCell>
                            <Sheet>
                              <SheetTrigger asChild>
                                <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                                  <Eye className="h-3 w-3" />
                                </Button>
                              </SheetTrigger>
                              <SheetContent side="right" className="max-w-4xl">
                                <SheetHeader>
                                  <SheetTitle>Full Row Data</SheetTitle>
                                  <SheetDescription>Row {index + 1} - Complete View</SheetDescription>
                                </SheetHeader>
                                <div className="mt-4 max-h-[80vh] overflow-auto">
                                  <JsonView data={row as Record<string, unknown>} shouldExpandNode={() => true} />
                                </div>
                              </SheetContent>
                            </Sheet>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        )}
      </CardContent>
    </Card>
  );
}
