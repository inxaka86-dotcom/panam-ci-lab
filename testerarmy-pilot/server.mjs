import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), 'fixture');
const routes = new Map([
  ['/', 'index.html'],
  ['/about.html', 'about.html'],
]);
const server = createServer(async (request, response) => {
  const path = new URL(request.url ?? '/', 'http://127.0.0.1').pathname;
  if (request.method !== 'GET' || !routes.has(path)) {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    response.end('Not found');
    return;
  }
  try {
    const content = await readFile(join(root, routes.get(path)));
    response.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
    });
    response.end(content);
  } catch {
    response.writeHead(500);
    response.end('Fixture unavailable');
  }
});
server.listen(4317, '127.0.0.1');
process.on('SIGTERM', () => server.close());
