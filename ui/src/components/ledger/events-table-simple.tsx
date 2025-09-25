'use client';

import { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useReactTable, getCoreRowModel, flexRender, createColumnHelper } from '@tanstack/react-table';
import { apiClient, PMMEvent } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { databases, defaultDatabase } from '@/lib/databases';

const columnHelper = createColumnHelper<PMMEvent>();

export function EventsTable() {
  const [selectedDb, setSelectedDb] = useState(defaultDatabase);
  const [kindFilter] = useState('all'); // setKindFilter removed for now
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['events', '.data/pmm.db', kindFilter],
    queryFn: () => {
      console.log('Fetching events from LIVE DATABASE ONLY: .data/pmm.db');
      return apiClient.getEvents({
        db: '.data/pmm.db', // HARDCODED - ONLY LIVE DATABASE
        kind: kindFilter === 'all' ? undefined : kindFilter,
        limit: 50,
      });
    },
    staleTime: 0, // Always refetch
    gcTime: 0, // Don't cache
  });

  // Clear cache on mount to ensure fresh data
  useEffect(() => {
    queryClient.clear();
  }, [queryClient]);

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['events'] });
  };

  const columns = [
    columnHelper.accessor('id', {
      header: 'ID',
      cell: (info) => <Badge variant="outline">{info.getValue()}</Badge>,
    }),
    columnHelper.accessor('kind', {
      header: 'Kind',
      cell: (info) => <Badge variant="secondary">{info.getValue()}</Badge>,
    }),
    columnHelper.accessor('ts', {
      header: 'Timestamp',
      cell: (info) => <span className="text-sm">{new Date(info.getValue()).toLocaleString()}</span>,
    }),
    columnHelper.accessor('content', {
      header: 'Content',
      cell: (info) => {
        const content = info.getValue();
        return content ? (
          <span className="text-sm">{content.substring(0, 100)}...</span>
        ) : <span className="text-muted-foreground">—</span>;
      },
    }),
  ];

  const table = useReactTable({
    data: data?.events || [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (error) {
    return <Card><CardContent><p className="text-destructive">Error loading events</p></CardContent></Card>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Live PMM Database</CardTitle>
          <CardDescription>
            Source: <code className="text-xs bg-muted px-1 py-0.5 rounded">.data/pmm.db</code>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={handleRefresh} variant="outline">
            Refresh Data
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Events ({data?.events.length || 0})</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <TableHead key={header.id}>
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={4}>Loading...</TableCell></TableRow>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
