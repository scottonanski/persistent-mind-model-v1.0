# Testing Status Messages

## What Was Implemented

Added state-based status messages to show users what PMM is doing during post-processing.

## Status Messages

- 💭 **Thinking...** - Default/initial processing
- ✨ **Evolving...** - Stage transitions
- 📊 **Analyzing commitments...** - Processing commitments
- 🤔 **Reflecting...** - During reflection check
- 😕 **Hmm, something unexpected...** - On errors

## How to Test

1. **Start PMM:**
   ```bash
   python -m pmm.cli.chat
   ```

2. **Normal chat** (should see "💭 Thinking..." briefly):
   ```
   > Hello
   ASSISTANT Hello there...
   💭 Thinking...
   > 
   ```

3. **Trigger stage change** (should see "✨ Evolving..."):
   - Have a longer conversation
   - Watch for stage transitions

4. **Trigger reflection** (should see "🤔 Reflecting..."):
   - Reflection happens based on novelty/cadence
   - May take 1-2 seconds when it triggers

5. **Check for commitments** (should see "📊 Analyzing commitments..."):
   - When PMM creates commitments from reflection

## Expected Behavior

✅ Status appears after response completes  
✅ Status updates based on what's happening  
✅ Status clears before prompt appears  
✅ No mysterious delays - everything explained  
✅ Errors show friendly "confused" message  

## Notes

- Status messages are brief (cleared quickly)
- Multiple statuses may show in sequence
- Errors show for 0.5s before clearing
- All logging is at WARNING level by default
