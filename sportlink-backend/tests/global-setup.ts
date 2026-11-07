import { execSync } from 'node:child_process';
import { rmSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(__dirname, '..');
const TEST_DATABASE_URL = 'file:./test.db';

/** Applies the committed migration to a fresh, isolated test database. */
export default function setup() {
  rmSync(resolve(ROOT, 'prisma', 'test.db'), { force: true });
  execSync('npx prisma migrate deploy', {
    cwd: ROOT,
    env: { ...process.env, DATABASE_URL: TEST_DATABASE_URL },
    stdio: 'pipe',
  });
}
