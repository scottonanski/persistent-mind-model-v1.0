'use client';

import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { BookOpen, MessageSquare, Brain } from 'lucide-react';
import { useDatabase } from '@/lib/database-context';
import { apiClient } from '@/lib/api';
import { getEventLabel } from '@/lib/event-labels';
import { format, parseISO } from 'date-fns';

import type { PMMEvent } from '@/lib/api';

export function ReflectionsFeed() {
  const { selectedDb } = useDatabase();
  const [typeFilter, setTypeFilter] = useState('all');

  const { data: reflections, isLoading, error } = useQuery({
    queryKey: ['reflections', selectedDb],
    queryFn: () => apiClient.getReflections({ db: selectedDb, limit: 10 }),
    refetchInterval: 60000,
  });

  const filteredReflections = reflections?.reflections.filter(reflection => {
    if (typeFilter === 'all') return true;
    return reflection.kind === typeFilter;
  }) || [];

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Reflections Feed
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="h-8 w-8 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-3/4" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Reflections Feed
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-destructive text-sm">Failed to load reflections</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpen className="h-5 w-5" />
          Reflections Feed
        </CardTitle>
        <CardDescription>Recent thoughts and meta-reflections</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="reflection">Reflections</SelectItem>
            <SelectItem value="meta_reflection">Meta-Reflections</SelectItem>
          </SelectContent>
        </Select>

        <div className="space-y-4 max-h-64 overflow-y-auto">
          {filteredReflections.map((reflection: PMMEvent, index: number) => {
            const isMetaReflection = reflection.kind === 'meta_reflection';
            const label = getEventLabel(reflection);
            const excerpt = label.length > 100 ? label.substring(0, 100) + '...' : label;
            
            return (
              <motion.div
                key={reflection.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                className="border-b border-border last:border-b-0 pb-4 last:pb-0"
              >
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-full ${isMetaReflection ? 'bg-purple-100 dark:bg-purple-900' : 'bg-blue-100 dark:bg-blue-900'}`}>
                    {isMetaReflection ? (
                      <Brain className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                    ) : (
                      <MessageSquare className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    )}
                  </div>
                  
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      <Badge variant={isMetaReflection ? 'secondary' : 'outline'}>
                        {isMetaReflection ? 'Meta' : 'Reflection'}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {format(parseISO(reflection.ts), 'MMM dd, HH:mm')}
                      </span>
                    </div>
                    
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {excerpt}
                    </p>
                  </div>
                </div>
              </motion.div>
            );
          })}
          
          {filteredReflections.length === 0 && (
            <p className="text-center text-muted-foreground py-8">
              No reflections found
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
