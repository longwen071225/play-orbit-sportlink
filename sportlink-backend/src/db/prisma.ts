// Side-effect import: loads .env before the client resolves DATABASE_URL.
import '../config/env';
import { PrismaClient } from '@prisma/client';
import { env } from '../config/env';

export const prisma = new PrismaClient({
  log: env.isTest ? [] : ['warn', 'error'],
});
