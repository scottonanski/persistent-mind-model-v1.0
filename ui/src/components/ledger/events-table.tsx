'use client';

import { useState, useEffect, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useReactTable, getCoreRowModel, flexRender, createColumnHelper, SortingState, getSortedRowModel, VisibilityState } from '@tanstack/react-table';
import { apiClient, PMMEvent } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { JsonView } from 'react-json-view-lite';
import { ChevronDown, ChevronRight, Settings, Eye, RefreshCw, Filter, AlertTriangle } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { Skeleton } from '@/components/ui/skeleton';
import { getEventLabel } from '@/lib/event-labels';

const columnHelper = createColumnHelper<PMMEvent>();

const eventKinds = [
  'all',
  'identity_adopt',
  'identity_change',
  'commitment_open',
  'commitment_close',
  'commitment_expire',
  'reflection',
  'meta_reflection',
  'autonomy_tick',
  'invariant_violation',
  'metrics_update',
  'evaluation_report',
  'stage_progress',
  'curriculum_update',
  'bandit_reward',
  'bandit_arm_chosen',
  'llm_latency',
  'name_attempt_user',
  'self_suggestion',
];

export function EventsTable() {
  const { selectedDb } = useDatabase();
  const [kindFilter, setKindFilter] = useState('all');
  const [sinceDate, setSinceDate] = useState('');
  const [untilDate, setUntilDate] = useState('');
  const [limit, setLimit] = useState(50);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({
    id: true,
    ts: true,
    kind: true,
    content: true,
    meta: true,
    hash: true,
    prev_hash: true,
    actions: true,
  });
  const [showHashChain, setShowHashChain] = useState(true);

  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['events', selectedDb, kindFilter, sinceDate, untilDate, limit],
    queryFn: () => {
      console.log(`Fetching events from database: ${selectedDb}`);
      return apiClient.getEvents({
        db: selectedDb,
        kind: kindFilter === 'all' ? undefined : kindFilter,
        since_ts: sinceDate || undefined,
        until_ts: untilDate || undefined,
        limit,
      });
    },
    staleTime: 30000, // 30 seconds
    gcTime: 5 * 60 * 1000, // 5 minutes
  });

  // Clear cache on mount to ensure fresh data
  useEffect(() => {
    queryClient.clear();
  }, [queryClient]);

  // Keyboard shortcuts
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    // Only handle shortcuts when not typing in an input
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
      return;
    }

    switch (event.key) {
      case '/':
        event.preventDefault();
        // Focus the kind filter
        const kindFilter = document.getElementById('kind-filter');
        if (kindFilter) kindFilter.focus();
        break;
      case 'r':
        if (event.ctrlKey || event.metaKey) {
          event.preventDefault();
          handleRefresh();
        }
        break;
      case 'Escape':
        // Close any open sheets/modals
        const closeButtons = document.querySelectorAll('[data-sheet-close]');
        closeButtons.forEach(button => (button as HTMLElement).click());
        break;
    }
  }, []);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const handleRefresh = () => {
    refetch();
  };

  const handleResetFilters = () => {
    setKindFilter('all');
    setSinceDate('');
    setUntilDate('');
    setLimit(50);
  };

  const columns = [
    columnHelper.accessor('id', {
      header: 'ID',
      cell: (info) => <Badge variant="outline">{info.getValue()}</Badge>,
      sortingFn: 'alphanumeric',
    }),
    columnHelper.accessor('ts', {
      header: 'Timestamp',
      cell: (info) => {
        const date = parseISO(info.getValue());
        return (
          <span className="font-mono text-sm" title={info.getValue()}>
            {format(date, 'MMM dd HH:mm:ss')}
          </span>
        );
      },
      sortingFn: 'datetime',
    }),
    columnHelper.accessor('kind', {
      header: 'Kind',
      cell: (info) => <Badge variant="secondary">{info.getValue()}</Badge>,
      sortingFn: 'alphanumeric',
    }),
    columnHelper.accessor('content', {
      header: 'Content',
      cell: (info) => {
        const event = info.row.original;
        const label = getEventLabel(event);

        const truncated = label.length > 80 ? label.substring(0, 80) + '...' : label;
        return (
          <span className="text-sm" title={label}>
            {truncated}
          </span>
        );
      },
      sortingFn: 'alphanumeric',
    }),
    columnHelper.display({
      id: 'meta',
      header: 'Meta',
      cell: ({ row }) => {
        const meta = row.original.meta;
        if (!meta || (typeof meta === 'object' && Object.keys(meta).length === 0)) {
          return <span className="text-muted-foreground">—</span>;
        }

        return (
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="h-6 px-2 text-xs">
                View JSON
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="max-w-2xl">
              <div>
                <SheetHeader>
                  <SheetTitle>Event Meta Data</SheetTitle>
                  <SheetDescription>
                    Event ID: {row.original.id} | Kind: {row.original.kind}
                  </SheetDescription>
                </SheetHeader>
                <div className="mt-4 max-h-[80vh] overflow-auto">
                  <JsonView data={meta} shouldExpandNode={() => false} />
                </div>
              </div>
            </SheetContent>
          </Sheet>
        );
      },
    }),
    columnHelper.accessor('hash', {
      header: 'Hash',
      cell: (info) => {
        const hash = info.getValue();
        if (!hash) return <span className="text-muted-foreground">—</span>;
        
        return (
          <span className="font-mono text-xs" title={hash}>
            {hash.substring(0, 8)}...
          </span>
        );
      },
      sortingFn: 'alphanumeric',
    }),
    columnHelper.display({
      id: 'prev_hash',
      header: 'Prev Hash',
      cell: ({ row }) => {
        const prevHash = row.original.prev_hash;
        const currentHash = row.original.hash;
        
        if (!prevHash) return <span className="text-muted-foreground">—</span>;
        
        if (showHashChain && prevHash && currentHash) {
          return (
            <div className="flex items-center gap-1 font-mono text-xs">
              <span title={prevHash}>{prevHash.substring(0, 6)}...</span>
              <span className="text-muted-foreground">→</span>
              <span title={currentHash}>{currentHash.substring(0, 6)}...</span>
            </div>
          );
        }
        
        return (
          <span className="font-mono text-xs" title={prevHash}>
            {prevHash.substring(0, 8)}...
          </span>
        );
      },
    }),
    columnHelper.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="sm" className="h-6 px-2">
              <Eye className="h-3 w-3" />
            </Button>
          </SheetTrigger>
          <SheetContent side="right" className="max-w-4xl">
            <div>
              <SheetHeader>
                <SheetTitle>Full Event Details</SheetTitle>
                <SheetDescription>
                  Event ID: {row.original.id} | Kind: {row.original.kind}
                </SheetDescription>
              </SheetHeader>
              <div className="mt-4 space-y-4">
                <div>
                  <Label className="text-sm font-medium">Timestamp</Label>
                  <p className="font-mono text-sm">{row.original.ts}</p>
                </div>
                <div>
                  <Label className="text-sm font-medium">Summary</Label>
                  <p className="text-sm whitespace-pre-wrap">{getEventLabel(row.original)}</p>
                </div>
                <div>
                  <Label className="text-sm font-medium">Full Content</Label>
                  <p className="text-sm whitespace-pre-wrap">{row.original.content || 'No raw content'}</p>
                </div>
                <div>
                  <Label className="text-sm font-medium">Meta Data</Label>
                  <div className="mt-2 max-h-96 overflow-auto border rounded p-2">
                    <JsonView data={row.original.meta || {}} shouldExpandNode={() => false} />
                  </div>
                </div>
              </div>
            </div>
          </SheetContent>
        </Sheet>
      ),
    }),
  ];

  const table = useReactTable({
    data: data?.events || [],
    columns,
    state: {
      sorting,
      columnVisibility,
    },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (error) {
    return (
      <div className="space-y-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-center space-y-4">
              <div className="flex items-center justify-center">
                <AlertTriangle className="h-12 w-12 text-destructive" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">Failed to Load Events</h3>
                <p className="text-muted-foreground">
                  {error instanceof Error ? error.message : 'Unknown error occurred'}
                </p>
              </div>
              <div className="flex gap-2 justify-center">
                <Button onClick={handleRefresh}>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Try Again
                </Button>
                <Button variant="outline" onClick={handleResetFilters}>
                  <Filter className="h-4 w-4 mr-2" />
                  Reset Filters
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <Card>
        <CardHeader>
          <CardTitle>PMM Database Events</CardTitle>
          <CardDescription>
            Source: <code className="text-xs bg-muted px-1 py-0.5 rounded">{selectedDb}</code>
            {data && ` • ${data.events.length} events loaded`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-[150px]">
              <Label htmlFor="kind-filter">Event Kind</Label>
              <Select value={kindFilter} onValueChange={setKindFilter}>
                <SelectTrigger id="kind-filter">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {eventKinds.map((kind) => (
                    <SelectItem key={kind} value={kind}>
                      {kind === 'all' ? 'All Events' : kind}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="min-w-[140px]">
              <Label htmlFor="since-date">Since</Label>
              <Input
                id="since-date"
                type="datetime-local"
                value={sinceDate}
                onChange={(e) => setSinceDate(e.target.value)}
              />
            </div>

            <div className="min-w-[140px]">
              <Label htmlFor="until-date">Until</Label>
              <Input
                id="until-date"
                type="datetime-local"
                value={untilDate}
                onChange={(e) => setUntilDate(e.target.value)}
              />
            </div>

            <div className="w-20">
              <Label htmlFor="limit">Limit</Label>
              <Input
                id="limit"
                type="number"
                value={limit}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  // Prevent limit=0 which causes API errors
                  if (value > 0) {
                    setLimit(value);
                  } else if (e.target.value === '') {
                    // Allow empty temporarily, will reset to minimum
                    setLimit(1);
                  }
                }}
                min={1}
                max={1000}
              />
            </div>

            <div className="flex gap-2">
              <Button onClick={handleRefresh} variant="outline">
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </Button>
              <Button onClick={handleResetFilters} variant="outline">
                <Filter className="h-4 w-4 mr-2" />
                Reset
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Column Controls */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Column Visibility
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4">
            {table.getAllColumns().map((column) => (
              <div key={column.id} className="flex items-center space-x-2">
                <Checkbox
                  id={column.id}
                  checked={columnVisibility[column.id] ?? true}
                  onCheckedChange={(checked) => {
                    setColumnVisibility((prev) => ({
                      ...prev,
                      [column.id]: checked === true,
                    }));
                  }}
                />
                <Label htmlFor={column.id} className="text-sm">
                  {column.id === 'ts' ? 'Timestamp' : 
                   column.id === 'prev_hash' ? 'Prev Hash' :
                   column.id.charAt(0).toUpperCase() + column.id.slice(1)}
                </Label>
              </div>
            ))}
            <div className="flex items-center space-x-2 ml-4">
              <Checkbox
                id="hash-chain"
                checked={showHashChain}
                onCheckedChange={(checked) => setShowHashChain(checked === true)}
              />
              <Label htmlFor="hash-chain" className="text-sm">Hash Chain</Label>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Events Table */}
      <Card>
        <CardHeader>
          <CardTitle>Events</CardTitle>
          <CardDescription>
            {isLoading ? 'Loading events...' : `${data?.events.length || 0} events displayed`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : (
                            <div className="flex items-center space-x-1">
                              <span>{flexRender(header.column.columnDef.header, header.getContext())}</span>
                              {header.column.getCanSort() && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 w-6 p-0"
                                  onClick={header.column.getToggleSortingHandler()}
                                >
                                  {header.column.getIsSorted() === 'asc' && <ChevronDown className="h-3 w-3" />}
                                  {header.column.getIsSorted() === 'desc' && <ChevronRight className="h-3 w-3" />}
                                  {!header.column.getIsSorted() && <div className="h-3 w-3 border border-muted-foreground/30 rounded-sm" />}
                                </Button>
                              )}
                            </div>
                          )}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
            </Table>

            {/* Scrollable Table Body */}
            <div className="flex-1 overflow-auto min-h-0">
              <Table>
                <TableBody>
                  {isLoading ? (
                    // Loading skeleton rows
                    Array.from({ length: 5 }).map((_, index) => (
                      <TableRow key={`skeleton-${index}`}>
                        {table.getAllColumns().map((column) => (
                          <TableCell key={column.id}>
                            <Skeleton className="h-4 w-full" />
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  ) : table.getRowModel().rows?.length ? (
                    table.getRowModel().rows.map((row) => (
                      <TableRow key={row.id}>
                        {row.getVisibleCells().map((cell) => (
                          <TableCell key={cell.id}>
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={table.getAllColumns().length} className="h-24 text-center">
                        No events found.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
