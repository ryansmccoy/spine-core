# Tier-Aware UI Behavior

> Part of: [Dashboard Design](00-index.md)

## Design Principle

**Do NOT hide features randomly.**

Users should always understand:
1. What features exist
2. Which features they have access to
3. Why certain features require upgrade
4. How to upgrade if desired

---

## Tier Definitions

| Tier | Target User | Key Capabilities |
|------|-------------|------------------|
| **Basic** | Individual developer, learning | Sync execution, data browsing, manual triggers |
| **Intermediate** | Small team, production use | Execution history, scheduling, quality checks |
| **Advanced** | Enterprise, mission-critical | Auth, alerting, lineage, multi-tenant |

---

## UI Patterns by Tier Status

### Pattern 1: Available Feature

Feature is available in current tier.

```
┌─────────────────────────────────────────┐
│  [▶ Run Pipeline]                       │
│                                         │
│  Standard button, fully functional      │
└─────────────────────────────────────────┘
```

### Pattern 2: Upgrade Required (Visible)

Feature exists but requires higher tier. **Show it, explain why.**

```
┌─────────────────────────────────────────┐
│  Execution History                      │
│  ══════════════════                     │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ 🔒 Requires Intermediate Tier     │ │
│  │                                   │ │
│  │ Execution history allows you to:  │ │
│  │ • View past runs and their status │ │
│  │ • Debug failures with full logs   │ │
│  │ • Track success rates over time   │ │
│  │                                   │ │
│  │ [Learn More]  [Upgrade]           │ │
│  └───────────────────────────────────┘ │
│                                         │
└─────────────────────────────────────────┘
```

### Pattern 3: Coming Soon

Feature is planned but not yet implemented.

```
┌─────────────────────────────────────────┐
│  Data Lineage                           │
│  ════════════                           │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ 🚧 Coming in Advanced Tier        │ │
│  │                                   │ │
│  │ Track data from source to output. │ │
│  │ Expected: Q2 2026                 │ │
│  │                                   │ │
│  │ [Join Waitlist]                   │ │
│  └───────────────────────────────────┘ │
│                                         │
└─────────────────────────────────────────┘
```

### Pattern 4: Graceful Degradation

Feature partially works at lower tiers.

```
┌─────────────────────────────────────────┐
│  Data Readiness                         │
│  ══════════════                         │
│                                         │
│  Basic View (current tier):             │
│  • Latest week available: 2025-12-22    │
│  • Symbol count: 2,847                  │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ 💡 Upgrade for detailed readiness │ │
│  │                                   │ │
│  │ With Intermediate, you also get: │ │
│  │ • Week-by-week certification      │ │
│  │ • Anomaly integration             │ │
│  │ • Dependency tracking             │ │
│  │                                   │ │
│  │ [Upgrade]                         │ │
│  └───────────────────────────────────┘ │
│                                         │
└─────────────────────────────────────────┘
```

---

## Navigation Behavior by Tier

### Basic Tier Navigation

```
SIDEBAR
═══════

Overview          ✓ Accessible
Pipelines         ✓ Accessible  
Executions        🔒 Locked (shows upgrade message)
───────────
Data Readiness    ⚡ Basic version
Quality           🔒 Locked
Assets            ✓ Accessible
───────────
Settings          ✓ Accessible
```

### Intermediate Tier Navigation

```
SIDEBAR
═══════

Overview          ✓ Accessible
Pipelines         ✓ Accessible (+ history, scheduling)
Executions        ✓ Accessible
───────────
Data Readiness    ✓ Full version
Quality           ✓ Accessible
Assets            ✓ Accessible (+ derived analytics)
───────────
Settings          ✓ Accessible (+ notifications placeholder)
```

### Advanced Tier Navigation

```
SIDEBAR
═══════

Overview          ✓ Full with alerts
Pipelines         ✓ Full with SLAs
Executions        ✓ Full with lineage
───────────
Data Readiness    ✓ Full with audit
Quality           ✓ Full with custom rules
Assets            ✓ Full with lineage
───────────
Alerting          ✓ NEW PAGE
Users             ✓ NEW PAGE
Settings          ✓ Full
```

---

## Global Tier Indicator

Always show current tier in header:

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo] Market Spine    [●]    [BASIC]    [User ▾]              │
│                         health  tier                             │
└─────────────────────────────────────────────────────────────────┘
```

Tier badge is clickable → opens tier comparison modal.

---

## Tier Comparison Modal

```
┌─────────────────────────────────────────────────────────────────┐
│  Compare Tiers                                          [×]     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  You are currently on: BASIC                                    │
│                                                                  │
│                    │ Basic  │ Intermediate │ Advanced │         │
│  ──────────────────┼────────┼──────────────┼──────────┤         │
│  Sync Execution    │   ✓    │      ✓       │    ✓     │         │
│  Manual Triggers   │   ✓    │      ✓       │    ✓     │         │
│  Data Browsing     │   ✓    │      ✓       │    ✓     │         │
│  ──────────────────┼────────┼──────────────┼──────────┤         │
│  Execution History │   ✗    │      ✓       │    ✓     │         │
│  Scheduling        │   ✗    │      ✓       │    ✓     │         │
│  Async Execution   │   ✗    │      ✓       │    ✓     │         │
│  Quality Checks    │   ✗    │      ✓       │    ✓     │         │
│  ──────────────────┼────────┼──────────────┼──────────┤         │
│  Authentication    │   ✗    │      ✗       │    ✓     │         │
│  Alerting          │   ✗    │      ✗       │    ✓     │         │
│  Data Lineage      │   ✗    │      ✗       │    ✓     │         │
│  Multi-tenant      │   ✗    │      ✗       │    ✓     │         │
│                                                                  │
│              [Stay on Basic]        [Upgrade →]                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Specific Feature Gating

### Execution History

**Basic**: Not available
```tsx
<FeatureGate 
  feature="hasExecutionHistory"
  fallback={<TierUpgradeMessage 
    feature="Execution History" 
    requiredTier="intermediate"
    benefits={[
      "View past runs and their status",
      "Debug failures with full logs",
      "Track success rates over time"
    ]}
  />}
>
  <ExecutionHistoryTable />
</FeatureGate>
```

### Scheduling

**Basic**: Not available
```tsx
// Pipeline detail page
{capabilities?.hasScheduling ? (
  <ScheduleTab pipeline={pipeline} />
) : (
  <ScheduleUpgradePrompt />
)}
```

### Quality Dashboard

**Basic**: Not available
```tsx
// Navigation item
<NavItem 
  to="/dashboard/quality"
  locked={!capabilities?.hasQualityChecks}
  lockedMessage="Requires Intermediate tier"
/>
```

### Alerting

**Basic, Intermediate**: Not available
```tsx
// Only show in Advanced
{tier === 'advanced' && (
  <NavItem to="/dashboard/alerting">Alerting</NavItem>
)}
```

---

## Upgrade Prompts

### Contextual Upgrade

When user tries to access locked feature:

```
┌─────────────────────────────────────────┐
│  🔒 Scheduling                          │
│                                         │
│  Schedule your pipelines to run         │
│  automatically.                         │
│                                         │
│  Available in: Intermediate, Advanced   │
│                                         │
│  With scheduling, you can:              │
│  • Run pipelines on a cron schedule     │
│  • Get alerts when scheduled runs fail  │
│  • Track on-time vs late execution      │
│                                         │
│  [Learn More]  [Upgrade to Intermediate]│
│                                         │
└─────────────────────────────────────────┘
```

### Subtle Upsell

In settings or after completing a task:

```
┌─────────────────────────────────────────┐
│  ✓ Pipeline executed successfully       │
│                                         │
│  💡 Tip: With Intermediate tier, you    │
│  can schedule this to run automatically │
│  every week.                            │
│                                         │
│  [Maybe Later]  [Tell Me More]          │
└─────────────────────────────────────────┘
```

---

## Implementation Guidelines

### React Component Pattern

```tsx
// FeatureGate component
interface FeatureGateProps {
  feature: keyof SpineCapabilities;
  fallback?: React.ReactNode;
  children: React.ReactNode;
}

function FeatureGate({ feature, fallback, children }: FeatureGateProps) {
  const { capabilities } = useSpine();
  
  if (!capabilities?.[feature]) {
    return fallback ?? <DefaultUpgradeMessage feature={feature} />;
  }
  
  return <>{children}</>;
}
```

### Tier-Aware Hooks

```tsx
function useTierAwareData(feature: string, fetcher: () => Promise<T>) {
  const { capabilities, tier } = useSpine();
  
  // Return mock/limited data for lower tiers
  if (!capabilities?.[feature]) {
    return { data: null, isLocked: true, requiredTier: getRequiredTier(feature) };
  }
  
  // Fetch real data for enabled tiers
  return useQuery({
    queryKey: [feature],
    queryFn: fetcher,
  });
}
```

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Better Approach |
|--------------|--------------|-----------------|
| Hide nav items silently | User doesn't know features exist | Show locked with explanation |
| "Coming soon" everywhere | Feels like incomplete product | Only for actually planned features |
| Aggressive upgrade popups | Annoying, reduces trust | Contextual, dismissible prompts |
| Different UI layouts per tier | Confusing when upgrading | Same layout, gated content |
| No explanation for locks | User frustrated, can't evaluate | Always explain value + tier needed |
