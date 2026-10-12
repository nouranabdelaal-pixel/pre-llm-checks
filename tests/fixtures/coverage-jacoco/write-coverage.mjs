// Writes a synthetic JaCoCo XML report for fixture testing.
import { mkdirSync, writeFileSync } from 'node:fs';

mkdirSync('coverage', { recursive: true });

// LINE: missed=15, covered=85 → 85% line coverage
// BRANCH: missed=10, covered=40 → 80% branch coverage
const xml = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">
<report name="coverage-jacoco">
  <counter type="INSTRUCTION" missed="20" covered="100"/>
  <counter type="LINE" missed="15" covered="85"/>
  <counter type="BRANCH" missed="10" covered="40"/>
  <counter type="METHOD" missed="2" covered="18"/>
  <counter type="CLASS" missed="0" covered="5"/>
</report>`;

writeFileSync('coverage/jacoco.xml', xml);
console.log('JaCoCo coverage written: 85 covered / 100 total lines = 85%');
