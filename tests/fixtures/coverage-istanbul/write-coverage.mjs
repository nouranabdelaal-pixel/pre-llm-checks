// Writes a synthetic Istanbul json-summary report for fixture testing.
import { mkdirSync, writeFileSync } from 'node:fs';

mkdirSync('coverage', { recursive: true });

const summary = {
  total: {
    lines:      { total: 100, covered: 85, skipped: 0, pct: 85.0 },
    statements: { total: 120, covered: 100, skipped: 0, pct: 83.33 },
    functions:  { total: 20,  covered: 18,  skipped: 0, pct: 90.0 },
    branches:   { total: 40,  covered: 30,  skipped: 0, pct: 75.0 }
  }
};

writeFileSync('coverage/coverage-summary.json', JSON.stringify(summary, null, 2));
console.log('Coverage written: 85% lines, 75% branches');
