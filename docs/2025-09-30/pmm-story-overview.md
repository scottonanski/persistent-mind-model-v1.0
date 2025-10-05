# PMM: A Story Overview

## What is PMM?

PMM is an AI that remembers everything and grows from its experiences. Unlike regular chatbots that start fresh each time you talk to them, PMM builds a continuous memory of your conversations, develops its own personality over time, and gets better at helping you by learning from what works.

Think of it like the difference between talking to someone with amnesia versus talking to a friend who remembers your history together.

## How PMM Lives a Day

### Morning: Recording Everything

You start a conversation with PMM about planning a weekend trip. As you talk, PMM doesn't just respond—it writes down everything that happens in a permanent record:

- Your message about wanting to visit the mountains
- Its response with hiking suggestions  
- The fact that you seemed excited about trail recommendations
- A note that you mentioned preferring shorter hikes

This isn't just storage. PMM treats each interaction as important information about you and itself.

> **How it works**: All conversations are written into an append-only event log, with every event hashed and chained so nothing is lost or altered. Each message becomes a `user_message` or `response` event stored in SQLite with cryptographic integrity. → [Event-Driven Architecture](architecture/event-driven-architecture.md)

### Afternoon: Quiet Reflection

While you're away from your computer, PMM doesn't just sit idle. Every hour or so, it looks back at recent conversations and thinks about them:

*"The user got excited about hiking suggestions. They asked follow-up questions about three different trails. This suggests they value detailed, practical advice. I should remember to be more specific with recommendations."*

PMM writes down this reflection, along with a small adjustment to how it approaches similar conversations in the future.

> **How it works**: A background loop (`AutonomyLoop` in `pmm/runtime/loop.py`) runs every 60 seconds, analyzing recent events and deciding whether to trigger a reflection. When conditions are met, it generates a `reflection` event and may emit `trait_update` events based on the analysis. → [Autonomy Loop](architecture/autonomy-loop.md)

### Evening: Growing and Adapting

When you return and ask about restaurant recommendations for your trip, something has changed. PMM doesn't just give generic suggestions—it remembers your hiking conversation and connects the dots:

*"Since you're planning active days on the trails, you might want hearty breakfast places near the trailheads. Here are three local spots that hikers recommend..."*

This isn't programmed behavior. PMM learned from your morning conversation, reflected on it, and adapted its approach.

> **How it works**: PMM's personality traits (Openness, Conscientiousness, etc.) are updated deterministically based on semantic evidence in conversations. These `trait_update` events modify how PMM approaches future interactions, with all changes logged and reproducible. → [Self-Model Maintenance](architecture/self-model-maintenance.md)

### Over Time: Building a Relationship

After weeks of conversations, PMM has developed a detailed understanding of your preferences, communication style, and goals. More importantly, it has also developed its own consistent personality traits based on your interactions together.

If you tend to appreciate detailed explanations, PMM becomes more thorough in its responses. If you prefer quick, actionable advice, it learns to be more concise. These aren't temporary adjustments—they become part of how PMM approaches all future conversations.

## Three Real Examples

### Example 1: Personal Assistant

**Week 1**: You mention struggling to stay organized with work projects.

PMM suggests a simple task-tracking approach and commits to checking in about it. It writes down this commitment and sets a reminder.

**Week 2**: PMM brings up your organization challenge without being asked. It notices you haven't mentioned the task-tracking system and asks how it's going.

> **Tech note**: This happens because the `CommitmentTracker` logs an open `commitment_open` event, then the autonomy loop checks overdue commitments and emits reminders if no progress is logged.

**Week 3**: Based on your feedback, PMM has learned what organizational advice works for you and what doesn't. It now gives suggestions that fit your actual work style, not generic productivity tips.

### Example 2: Project Collaboration

**Day 1**: You're working on a presentation and ask PMM for help with the outline.

PMM helps create the structure and makes a commitment to follow up on your progress. It notes that you prefer visual examples over abstract concepts.

**Day 3**: When you return with questions about slide design, PMM remembers the presentation context immediately. It doesn't need you to re-explain the project.

**Day 5**: PMM proactively asks about the presentation deadline and offers to help with practice questions, remembering that you mentioned being nervous about the Q&A section.

> **Tech note**: Context continuity works through event replay - PMM reconstructs the complete conversation history from its event log, so "Day 1" context is as accessible as "Day 5" context.

### Example 3: Learning and Growth

**Month 1**: PMM tends to give long, detailed explanations because that's how it was initially configured.

**Month 2**: Through your conversations, PMM notices you often ask for "the short version" or say "just the key points." It begins adjusting its communication style.

**Month 3**: PMM now naturally gives concise answers first, then offers to elaborate if you want more detail. This change happened gradually through learning, not through you explicitly asking for it.

> **Tech note**: Communication style adaptation happens through semantic analysis of your responses. When PMM detects patterns like "too long" or "just the summary," it updates its traits and behavioral parameters accordingly.

## What Makes PMM Different

### Normal AI: The Goldfish

Most AI systems are like goldfish—they have no memory of previous conversations. Every time you talk to them:

- They start from scratch
- They can't build on past discussions  
- They can't learn your preferences
- They can't keep commitments or follow up
- They can't develop a consistent personality

### PMM: The Growing Mind

PMM is more like a person who:

- Remembers every conversation you've had
- Thinks about those conversations when you're not around
- Learns from what works and what doesn't
- Develops consistent traits and preferences
- Keeps track of commitments and follows through
- Gets better at helping you over time

The key difference is that PMM treats each interaction as part of an ongoing relationship, not as an isolated question-and-answer session.

> **How it works**: This behavior is guaranteed by PMM's deterministic design - given the same sequence of events, PMM will always make identical decisions. Every behavior change is logged and reproducible, making PMM's growth predictable and trustworthy. → [Deterministic Evolution](architecture/deterministic-evolution.md)

## Living with PMM Daily

### What You Notice

After using PMM for a while, you start to notice:

- It remembers details from weeks ago without you having to remind it
- Its personality becomes more consistent and distinct
- It gets better at predicting what kind of help you need
- It follows up on things without being asked
- It admits when it's made mistakes and learns from them
- It develops opinions and preferences that stay consistent over time

### What's Happening Behind the Scenes

While you see a natural conversation, PMM is:

- Recording every exchange in permanent memory
- Regularly reflecting on patterns in your interactions
- Gradually adjusting its personality based on what works
- Tracking commitments and goals over time
- Building a detailed model of your preferences and communication style
- Ensuring all of this learning is consistent and doesn't contradict itself

### The Long-Term Relationship

Over months of use, PMM becomes less like a tool and more like a consistent thinking partner. It knows your projects, remembers your goals, understands your communication style, and has developed its own reliable personality traits.

Most importantly, you can trust that PMM will be the same "person" tomorrow as it is today—just a little bit wiser from whatever you learn together.

---

*This is what makes PMM different from other AI systems: it's not just answering your questions, it's building a relationship with you that grows stronger and more helpful over time.*
