// Writes a synthetic lcov.info report for fixture testing.
// LH=64, LF=80 → 80% line coverage; BRH=20, BRF=25 → 80% branch coverage
import { mkdirSync, writeFileSync } from 'node:fs';

mkdirSync('coverage', { recursive: true });

const lcov = `TN:
SF:index.js
LF:80
LH:64
BRDA:1,0,0,1
BRDA:1,0,1,0
BRF:25
BRH:20
end_of_record
`;

writeFileSync('coverage/lcov.info', lcov);
console.log('lcov coverage written: LH=64 LF=80 => 80%');
