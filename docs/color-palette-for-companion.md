# PMM Companion Color Palette

**Version:** 1.0  
**Date:** 2025-10-05  
**Source:** Extracted from `ui/src/components/chat/chat.tsx`

This document defines the official color theme for the PMM Companion UI. These colors must be maintained across all future UI development.

---

## Core Background Colors

### Primary Backgrounds
- **Main Container**: `#202125`
  - Used for: Chat window container, model sidebar, input area
  - CSS: `bg-[#202125]`

- **Secondary Background**: `#26272c`
  - Used for: Chat messages area, selected model state, hover states
  - CSS: `bg-[#26272c]`

- **Tertiary Background**: `#2c2d32`
  - Used for: Empty state cards, inactive elements
  - CSS: `bg-[#2c2d32]`

### Transparent Backgrounds
- **Transparent**: `transparent`
  - Used for: Input fields, unselected model buttons
  - CSS: `bg-transparent`

---

## Message Bubble Colors

### User Messages
- **Background**: Tailwind `primary` color
  - CSS: `bg-primary`
- **Text**: Tailwind `primary-foreground` color
  - CSS: `text-primary-foreground`

### Assistant Messages
- **Background**: Tailwind `card` color
  - CSS: `bg-card`
- **Text**: Tailwind `card-foreground` color
  - CSS: `text-card-foreground`
- **Border**: Ring with `border` color
  - CSS: `ring-1 ring-border`

---

## Border Colors

### Standard Borders
- **Primary Border**: Tailwind `border` color at 40% opacity
  - CSS: `border-border/40`
  - Used for: Main containers, dividers

- **Light Border**: Tailwind `border` color at 30% opacity
  - CSS: `border-border/30`
  - Used for: Subtle separations, empty state cards

- **Selected State Ring**: Tailwind `border` color with ring
  - CSS: `ring-1 ring-border`
  - Used for: Active/selected model indicator

---

## Text Colors

### Primary Text
- **Foreground**: Tailwind `foreground` color
  - CSS: `text-foreground`
  - Used for: Headers, primary content, model names

### Muted Text
- **Muted Foreground**: Tailwind `muted-foreground` color
  - CSS: `text-muted-foreground`
  - Used for: Descriptions, secondary info, model provider, helper text

- **Extra Muted**: Tailwind `muted-foreground` at 80% opacity
  - CSS: `text-muted-foreground/80`
  - Used for: Model descriptions, least important text

---

## State Colors

### Error States
- **Error Background**: Tailwind `destructive` at 10% opacity
  - CSS: `bg-destructive/10`

- **Error Border**: Tailwind `destructive` at 40% opacity
  - CSS: `border-destructive/40`

- **Error Text**: Tailwind `destructive` color
  - CSS: `text-destructive`

---

## Interactive States

### Hover Effects
- **Hover Background**: `#26272c`
  - CSS: `hover:bg-[#26272c]`
  - Used for: Model selection buttons

### Disabled States
- **Opacity**: 50% opacity
  - CSS: `disabled:opacity-50`
- **Cursor**: Not allowed cursor
  - CSS: `disabled:cursor-not-allowed`

---

## Border Radius

- **Extra Large**: `rounded-3xl`
  - Used for: Main chat container, model sidebar
  
- **Large**: `rounded-2xl`
  - Used for: Message bubbles, input area, cards

- **Medium**: `rounded-lg`
  - Used for: Model selection buttons

- **Small**: `rounded-md`
  - Used for: Error messages, small elements

---

## Shadow Effects

- **Large Shadow**: `shadow-lg`
  - Used for: Main containers, elevated panels

- **Small Shadow**: `shadow-sm`
  - Used for: Message bubbles

- **Inner Shadow**: `shadow-inner`
  - Used for: Empty state cards, inset effects

---

## Design Principles

1. **Dark Theme First**: All colors are optimized for dark mode
2. **Consistent Opacity**: Use `/40` for primary borders, `/30` for lighter borders, `/10` for backgrounds
3. **Semantic Colors**: Use Tailwind semantic colors (`primary`, `card`, `border`, etc.) for flexibility
4. **Hex Values**: Direct hex values (`#202125`, `#26272c`, `#2c2d32`) for specific brand colors
5. **Hierarchy**: Darker to lighter creates depth and visual hierarchy

---

## Usage Guidelines

### DO:
- ✅ Use exact hex values for the three main background colors
- ✅ Maintain opacity levels as specified
- ✅ Use Tailwind semantic colors for text and borders
- ✅ Keep shadow hierarchy consistent

### DON'T:
- ❌ Modify hex color values
- ❌ Change opacity percentages
- ❌ Introduce new background colors without documentation
- ❌ Use inline color values that bypass this palette

---

## Tailwind Configuration Reference

These colors rely on Tailwind CSS semantic tokens. Ensure your `tailwind.config.js` properly defines:

- `colors.primary` and `colors.primary.foreground`
- `colors.card` and `colors.card.foreground`
- `colors.border`
- `colors.foreground`
- `colors.muted.foreground`
- `colors.destructive` and `colors.destructive.foreground`

---

**Note**: This palette is locked and should not be modified without updating this document and getting team approval.
