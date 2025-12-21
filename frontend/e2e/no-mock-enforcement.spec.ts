/**
 * No-mock enforcement test.
 *
 * Fails CI if production page files contain hardcoded domain object arrays,
 * mock/fixture/sample data patterns, or fake placeholder data.
 *
 * Only `tests/` and `e2e/` directories are allowed to contain test fixtures.
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SRC_DIR = path.resolve(__dirname, '../src');

/** Patterns that indicate hardcoded/mock data in production code */
const FORBIDDEN_PATTERNS = [
  // Hardcoded arrays of domain objects
  /\[\s*\{\s*(?:run_id|pipeline|workflow_name|schedule_id|worker_id)\s*:/,
  // Mock/fixture/fake/dummy/sample keywords used as data
  /(?:const|let|var)\s+(?:mock|fake|dummy|sample|fixture)[A-Z]/i,
  /(?:mock|fake|dummy)(?:Data|Runs|Workflows|Schedules|Workers|Events|DLQ)\b/i,
  // Inline placeholder arrays with 3+ objects (likely hardcoded lists)
  /=\s*\[\s*\{[^}]{10,}\}\s*,\s*\{[^}]{10,}\}\s*,\s*\{/,
];

/** Files/dirs that are exempt */
const EXEMPT_DIRS = ['__tests__', '__mocks__', '.test.', '.spec.'];

function isExempt(filePath: string): boolean {
  return EXEMPT_DIRS.some((d) => filePath.includes(d));
}

function scanDir(dir: string): Array<{ file: string; line: number; match: string }> {
  const violations: Array<{ file: string; line: number; match: string }> = [];

  if (!fs.existsSync(dir)) return violations;

  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      violations.push(...scanDir(fullPath));
    } else if (
      (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) &&
      !isExempt(fullPath)
    ) {
      const content = fs.readFileSync(fullPath, 'utf-8');
      const lines = content.split('\n');
      for (let i = 0; i < lines.length; i++) {
        for (const pattern of FORBIDDEN_PATTERNS) {
          if (pattern.test(lines[i])) {
            violations.push({
              file: path.relative(SRC_DIR, fullPath),
              line: i + 1,
              match: lines[i].trim().slice(0, 80),
            });
          }
        }
      }
    }
  }

  return violations;
}

test.describe('No-mock enforcement', () => {
  test('production pages must not contain hardcoded mock data', () => {
    const pagesDir = path.join(SRC_DIR, 'pages');
    const violations = scanDir(pagesDir);

    if (violations.length > 0) {
      const report = violations
        .map((v) => `  ${v.file}:${v.line} → ${v.match}`)
        .join('\n');
      throw new Error(
        `Found ${violations.length} mock/hardcoded data violation(s) in production pages:\n${report}\n\n` +
          'Fixtures and mock data are only allowed in /tests/ and /e2e/ directories.',
      );
    }

    expect(violations).toHaveLength(0);
  });

  test('production components must not contain hardcoded mock data', () => {
    const componentsDir = path.join(SRC_DIR, 'components');
    const violations = scanDir(componentsDir);

    if (violations.length > 0) {
      const report = violations
        .map((v) => `  ${v.file}:${v.line} → ${v.match}`)
        .join('\n');
      throw new Error(
        `Found ${violations.length} mock/hardcoded data violation(s) in production components:\n${report}\n\n` +
          'Fixtures and mock data are only allowed in /tests/ and /e2e/ directories.',
      );
    }

    expect(violations).toHaveLength(0);
  });

  test('API hooks must not contain fallback fixture arrays', () => {
    const apiDir = path.join(SRC_DIR, 'api');
    const violations = scanDir(apiDir);

    if (violations.length > 0) {
      const report = violations
        .map((v) => `  ${v.file}:${v.line} → ${v.match}`)
        .join('\n');
      throw new Error(
        `Found ${violations.length} mock/hardcoded data violation(s) in API layer:\n${report}\n\n` +
          'API hooks must never silently fall back to fixture data.',
      );
    }

    expect(violations).toHaveLength(0);
  });
});
