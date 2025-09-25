// Quick test of the event summary generation
const { generateEventSummary, generateTooltipContent } = require('./src/lib/event-summaries.ts');

// Test events
const testEvents = [
  {
    kind: 'priority_update',
    content: '',
    meta: {
      ranking: [
        { cid: '2fcb557e33994ac58cbf092a8ceb09af', score: 0.78103319587728 }
      ]
    },
    ts: '2024-01-15T10:30:00Z'
  },
  {
    kind: 'stage_progress',
    content: '',
    meta: {
      stage: 'S4',
      IAS: 1.0,
      GAS: 1.0,
      commitment_count: 169,
      progress: 85
    },
    ts: '2024-01-15T10:31:00Z'
  },
  {
    kind: 'identity_adopt',
    content: '',
    meta: {
      name: 'Scott',
      confidence: 0.95
    },
    ts: '2024-01-15T10:32:00Z'
  },
  {
    kind: 'commitment_open',
    content: 'Work on PMM UI improvements',
    meta: {
      intent: 'Improve user experience',
      project: 'PMM Dashboard'
    },
    ts: '2024-01-15T10:33:00Z'
  }
];

console.log('Testing Event Summary Generation:\n');

testEvents.forEach((event, i) => {
  console.log(`${i + 1}. ${event.kind}:`);
  console.log(`   Summary: ${generateEventSummary(event)}`);
  console.log(`   Tooltip: ${generateTooltipContent(event)}`);
  console.log('');
});
