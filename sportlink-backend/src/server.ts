import { buildApp } from './app';
import { env } from './config/env';

async function main() {
  const app = await buildApp();
  try {
    await app.listen({ host: env.HOST, port: env.PORT });
    app.log.info(
      `SoloCoach AI backend listening on http://${env.HOST}:${env.PORT} (mockAI=${env.mockAI})`,
    );
    app.log.info(`API docs: http://localhost:${env.PORT}/documentation`);
  } catch (error) {
    app.log.error(error);
    process.exit(1);
  }
}

void main();
