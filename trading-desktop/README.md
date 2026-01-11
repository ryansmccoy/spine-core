# Trading Desktop

A React + TypeScript frontend for the Market Spine platform, providing a dashboard interface for pipeline management, data queries, and trading analytics.

## Quick Start

```bash
# Install dependencies
npm install

# Copy environment config
cp .env.local.example .env.local

# Start development server (with backend proxy)
npm run dev
```

The app will be available at `http://localhost:5173`.

## Frontend ↔ Backend API

The Trading Desktop connects to Market Spine backends using a capabilities-driven architecture that automatically adapts to the connected backend tier.

### Supported Backends

| Backend | Profile | Key Features |
|---------|---------|--------------|
| Basic | `basic` | Pipelines, weeks/symbols queries |
| Intermediate | `intermediate` | + Scheduler, calc queries |
| Advanced | `advanced` | + Anomaly detection, readiness, multi-version |

### Configuration

Set the backend URL in `.env.local`:

```env
VITE_MARKET_SPINE_BASE_URL=http://localhost:8000
```

### How It Works

1. **Capability Detection**: On startup, the frontend calls `GET /v1/capabilities` to discover available features
2. **Feature Gating**: UI components are shown/hidden based on capabilities
3. **Graceful Degradation**: Unavailable features show upgrade prompts instead of errors

### API Client Usage

```tsx
import { useSpine, FeatureGate } from './api';

function MyComponent() {
  const { client, hasFeature, isConnected } = useSpine();
  
  // Query data
  const weeks = await client.queryWeeks('otc');
  
  // Check features
  if (hasFeature('scheduler')) {
    // Show scheduler UI
  }
}

// Declarative feature gating
<FeatureGate feature="query_calcs" fallback={<UpgradePrompt />}>
  <CalcsPage />
</FeatureGate>
```

See [Frontend Setup Guide](../docs/frontend-setup.md) for detailed documentation.

---

## Technical Details

### React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
