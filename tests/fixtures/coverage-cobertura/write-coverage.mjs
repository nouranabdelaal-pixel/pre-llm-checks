// Writes a synthetic Cobertura XML report for fixture testing.
import { mkdirSync, writeFileSync } from 'node:fs';

mkdirSync('coverage', { recursive: true });

// line-rate=0.72 → 72% line coverage, branch-rate=0.60 → 60%
const xml = `<?xml version="1.0" ?>
<!DOCTYPE coverage SYSTEM "http://cobertura.sourceforge.net/xml/coverage-04.dtd">
<coverage line-rate="0.72" branch-rate="0.60" version="2.1" timestamp="1234567890">
  <packages>
    <package name="." line-rate="0.72" branch-rate="0.60" complexity="1.5">
      <classes>
        <class name="index.js" filename="index.js" line-rate="0.72" branch-rate="0.60">
          <lines/>
        </class>
      </classes>
    </package>
  </packages>
</coverage>`;

writeFileSync('coverage/cobertura.xml', xml);
console.log('Cobertura coverage written: line-rate=0.72 (72%)');
