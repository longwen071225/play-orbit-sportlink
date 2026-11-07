import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { buildApp } from '../src/app';

async function main() {
  const app = await buildApp();
  await app.ready();
  const spec = app.swagger();
  const docsDir = resolve(__dirname, '..', 'docs');
  mkdirSync(docsDir, { recursive: true });
  const out = resolve(docsDir, 'openapi.json');
  writeFileSync(out, `${JSON.stringify(spec, null, 2)}\n`, 'utf8');
  // eslint-disable-next-line no-console
  console.log(`OpenAPI 文档已生成: ${out}`);
  await app.close();
  process.exit(0);
}

void main();
