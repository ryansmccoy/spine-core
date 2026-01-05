# Frontend Contract Principles

> Rules for frontend-backend contracts in spine-core. Reference this when building React components that consume APIs.

## Core Principles

### 1. API Contracts Are Typed

Every API response should have a TypeScript interface:

```typescript
// types/prices.ts
interface PriceData {
  symbol: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change: number | null;
  change_percent: number | null;
}

interface PaginationMeta {
  offset: number;
  limit: number;
  total: number;
  has_more: boolean;
}

interface PriceResponse {
  data: PriceData[];
  pagination: PaginationMeta;
  capture?: {
    capture_id: string;
    captured_at: string;
  };
}
```

### 2. Fetch Functions, Not Direct fetch()

Wrap all API calls in typed functions:

```typescript
// api/prices.ts
export async function fetchPrices(
  symbol: string,
  options?: PriceQueryOptions
): Promise<PriceResponse> {
  const params = new URLSearchParams();
  if (options?.offset) params.set('offset', String(options.offset));
  if (options?.limit) params.set('limit', String(options.limit));
  
  const response = await fetch(`/v1/data/prices/${symbol}?${params}`);
  if (!response.ok) throw new ApiError(response);
  
  return response.json();
}
```

### 3. Error Handling Is Explicit

Never swallow errors silently:

```typescript
// api/errors.ts
export class ApiError extends Error {
  constructor(
    public response: Response,
    public code?: string,
    public details?: unknown
  ) {
    super(`API Error: ${response.status}`);
  }
}

// In components
try {
  const data = await fetchPrices('AAPL');
} catch (error) {
  if (error instanceof ApiError) {
    if (error.response.status === 404) {
      // Handle not found
    }
  }
  throw error; // Re-throw unexpected errors
}
```

### 4. Loading States Are Required

Every data-fetching component must handle:

- **Loading**: Show skeleton/spinner
- **Error**: Show error message with retry
- **Empty**: Show empty state message
- **Success**: Show data

```typescript
function PriceChart({ symbol }: { symbol: string }) {
  const { data, isLoading, error } = usePrices(symbol);
  
  if (isLoading) return <Skeleton />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!data?.length) return <EmptyState message="No price data" />;
  
  return <Chart data={data} />;
}
```

---

## Pagination Contracts

### Request Pattern

```typescript
interface PaginatedRequest {
  offset?: number;  // Default: 0
  limit?: number;   // Default: 100, Max: 1000
}
```

### Response Pattern

```typescript
interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    offset: number;
    limit: number;
    total: number;
    has_more: boolean;
  };
}
```

### Client-Side Pagination Hook

```typescript
function usePaginatedData<T>(
  fetchFn: (offset: number, limit: number) => Promise<PaginatedResponse<T>>,
  pageSize = 100
) {
  const [offset, setOffset] = useState(0);
  const [allData, setAllData] = useState<T[]>([]);
  
  const { data, isLoading } = useQuery({
    queryKey: ['data', offset],
    queryFn: () => fetchFn(offset, pageSize),
    onSuccess: (response) => {
      setAllData(prev => [...prev, ...response.data]);
    },
  });
  
  const loadMore = () => {
    if (data?.pagination.has_more) {
      setOffset(prev => prev + pageSize);
    }
  };
  
  return { data: allData, isLoading, loadMore, hasMore: data?.pagination.has_more };
}
```

---

## Date Handling

### Always Use ISO Strings

Backend returns ISO 8601 dates:

```json
{
  "date": "2024-01-15",
  "captured_at": "2024-01-15T12:00:00Z"
}
```

### Frontend Parsing

```typescript
// Parse date-only strings
const date = new Date(priceData.date + 'T00:00:00');

// Parse timestamps
const capturedAt = new Date(response.capture.captured_at);

// Format for display
const formatted = date.toLocaleDateString('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
});
```

---

## Caching Strategy

### Query Keys Include All Parameters

```typescript
const queryKey = ['prices', symbol, { offset, limit, startDate, endDate }];
```

### Stale-While-Revalidate

```typescript
const { data } = useQuery({
  queryKey: ['prices', symbol],
  queryFn: () => fetchPrices(symbol),
  staleTime: 5 * 60 * 1000,      // 5 minutes
  cacheTime: 30 * 60 * 1000,     // 30 minutes
});
```

### Invalidation on Mutation

```typescript
const mutation = useMutation({
  mutationFn: ingestPrices,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['prices'] });
  },
});
```

---

## Guardrails for LLMs

When generating frontend code:

1. ✅ Create TypeScript interfaces for all API responses
2. ✅ Use typed fetch wrapper functions
3. ✅ Handle loading, error, and empty states
4. ✅ Use ISO date strings, never locale-specific formats
5. ✅ Include pagination handling for list endpoints
6. ❌ Don't use `any` type for API responses
7. ❌ Don't call `fetch()` directly in components
8. ❌ Don't assume data exists without null checks
9. ❌ Don't hardcode API URLs (use constants/config)

---

## Type Generation

Consider generating types from OpenAPI spec:

```bash
# Generate types from OpenAPI
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts
```

This ensures frontend types match backend exactly.

---

## Checklist

Before submitting frontend changes:

- [ ] All API responses have TypeScript interfaces
- [ ] Fetch functions are properly typed
- [ ] Loading/error/empty states handled
- [ ] Pagination implemented for list views
- [ ] Dates parsed and formatted consistently
- [ ] Error boundaries in place
- [ ] Cache invalidation on data changes
