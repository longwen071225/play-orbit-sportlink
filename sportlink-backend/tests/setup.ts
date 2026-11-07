// Runs before each test file imports the app, so dotenv/config in env.ts
// will not override these values.
process.env.NODE_ENV = 'test';
process.env.DATABASE_URL = 'file:./test.db';
process.env.MOCK_AI = 'true';
process.env.CORS_ORIGIN = '*';
