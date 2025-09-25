'use client';

import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { CheckCircle, Clock, XCircle, Target } from 'lucide-react';
import { getEventLabel } from '@/lib/event-labels';
import { apiClient } from '@/lib/api';
import { useDatabase } from '@/lib/database-context';
import { format, parseISO } from 'date-fns';

interface CommitmentItemProps {
  commitment: any;
  index: number;
}

function CommitmentItem({ commitment, index }: CommitmentItemProps) {
  const isOpen = commitment.kind === 'commitment_open';
  const isClosed = commitment.kind === 'commitment_close';
  const isExpired = commitment.kind === 'commitment_expire';
  
  const text = getEventLabel(commitment);
  const priority = commitment.meta?.priority || 'medium';
  const source = commitment.meta?.source || 'unknown';
  
  const getStatusIcon = () => {
    if (isClosed) return <CheckCircle className="h-4 w-4 text-green-500" />;
    if (isExpired) return <XCircle className="h-4 w-4 text-red-500" />;
    return <Clock className="h-4 w-4 text-blue-500" />;
  };
  
  const getStatusColor = () => {
    if (isClosed) return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
    if (isExpired) return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
    return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
  };
  
  const getPriorityColor = () => {
    switch (priority) {
      case 'high': return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
      case 'medium': return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
      case 'low': return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
      default: return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200';
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.1 }}
      className="p-3 border rounded-lg space-y-2"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          {getStatusIcon()}
          <span className="font-medium text-sm">
            {isOpen ? 'Active' : isClosed ? 'Completed' : 'Expired'}
          </span>
        </div>
        <div className="flex gap-1">
          <Badge variant="outline" className={getPriorityColor()}>
            {priority}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {source}
          </Badge>
        </div>
      </div>
      
      <p className="text-sm text-muted-foreground leading-relaxed line-clamp-3">
        {text}
      </p>
      
      <div className="text-xs text-muted-foreground">
        {format(parseISO(commitment.ts), 'MMM dd, HH:mm')}
      </div>
    </motion.div>
  );
}

export function CommitmentsTracker() {
  const { selectedDb } = useDatabase();

  const { data: commitments, isLoading, error } = useQuery({
    queryKey: ['commitments', selectedDb],
    queryFn: () => apiClient.getCommitments({ db: selectedDb, limit: 20 }),
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5" />
            Commitments Tracker
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="p-3 border rounded-lg space-y-2">
                <div className="flex justify-between">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-4 w-16" />
                </div>
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-3 w-24" />
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
            <Target className="h-5 w-5" />
            Commitments Tracker
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-destructive text-sm">Failed to load commitments</p>
        </CardContent>
      </Card>
    );
  }

  const allCommitments = commitments?.commitments || [];
  const activeCommitments = allCommitments.filter(c => c.kind === 'commitment_open');
  const completedCommitments = allCommitments.filter(c => c.kind === 'commitment_close');
  const expiredCommitments = allCommitments.filter(c => c.kind === 'commitment_expire');

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Target className="h-5 w-5" />
          Commitments Tracker
        </CardTitle>
        <CardDescription>
          Active, completed, and expired commitments
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">{activeCommitments.length}</div>
            <div className="text-xs text-muted-foreground">Active</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">{completedCommitments.length}</div>
            <div className="text-xs text-muted-foreground">Completed</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-600">{expiredCommitments.length}</div>
            <div className="text-xs text-muted-foreground">Expired</div>
          </div>
        </div>

        {/* Recent Commitments */}
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {allCommitments.slice(0, 10).map((commitment, index) => (
            <CommitmentItem
              key={commitment.id}
              commitment={commitment}
              index={index}
            />
          ))}
          
          {allCommitments.length === 0 && (
            <p className="text-center text-muted-foreground py-8">
              No commitments found
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
