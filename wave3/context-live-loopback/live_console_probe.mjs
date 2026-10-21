import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';

import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { createMcpExpressApp, requireBearerAuth } from '@modelcontextprotocol/express';
import { toNodeHandler } from '@modelcontextprotocol/node';
import {
  createMcpHandler,
  McpServer,
  OAuthError,
  OAuthErrorCode,
} from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

const PROTOCOL = '2026-07-28';
const REQUIRED_SCOPE = 'mcp:read';
const TOOLS = ['context.current', 'context.status'];
const GOOD_TOKEN = randomBytes(32).toString('hex');
const NO_SCOPE_TOKEN = randomBytes(32).toString('hex');

const verifier = {
  async verifyAccessToken(token) {
    const expiresAt = Math.floor(Date.now() / 1000) + 300;
    if (token === GOOD_TOKEN) {
      return { token, clientId: 'public-live-console-probe', scopes: [REQUIRED_SCOPE], expiresAt };
    }
    if (token === NO_SCOPE_TOKEN) {
      return { token, clientId: 'public-live-console-probe-noscope', scopes: [], expiresAt };
    }
    throw new OAuthError(OAuthErrorCode.InvalidToken, 'unknown token');
  },
};

function buildServer() {
  const server = new McpServer(
    { name: 'public-live-console-mcp', version: '1.0.0' },
    {
      capabilities: { tools: {} },
      instructions: 'Synthetic read-only MCP source for a local live-console proof.',
    },
  );
  const annotations = {
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: false,
  };

  server.registerTool(
    'context.current',
    {
      description: 'Synthetic current-context snapshot',
      inputSchema: z.object({}),
      annotations,
    },
    async (_args, ctx) => {
      assert.equal(ctx.http?.authInfo?.clientId, 'public-live-console-probe');
      return {
        content: [{ type: 'text', text: 'synthetic current context' }],
        structuredContent: {
          ok: true,
          tool: 'context.current',
          authoritative: false,
          mutation_allowed: false,
          value: 'synthetic-current-context',
        },
      };
    },
  );

  server.registerTool(
    'context.status',
    {
      description: 'Synthetic read-only status',
      inputSchema: z.object({}),
      annotations,
    },
    async (_args, ctx) => {
      assert.equal(ctx.http?.authInfo?.clientId, 'public-live-console-probe');
      return {
        content: [{ type: 'text', text: 'synthetic status' }],
        structuredContent: {
          ok: true,
          tool: 'context.status',
          authoritative: false,
          mutation_allowed: false,
          fresh: true,
        },
      };
    },
  );

  return server;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderConsole(current, status) {
  const payload = escapeHtml(JSON.stringify({ current, status }, null, 2));
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Public Context Live Console Proof</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 72rem; }
    .badge { font-weight: 700; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; }
  </style>
</head>
<body>
  <h1>Public Context Live Console Proof</h1>
  <p class="badge">SYNTHETIC / READ ONLY / NON-AUTHORITATIVE</p>
  <p>Source: authenticated MCP transport only. No direct source access and no mutation surface.</p>
  <pre>${payload}</pre>
</body>
</html>`;
}

const app = createMcpExpressApp({ host: '127.0.0.1', allowedHosts: ['127.0.0.1'] });
app.disable('etag');
const auth = requireBearerAuth({ verifier, requiredScopes: [REQUIRED_SCOPE] });
const mcp = createMcpHandler(buildServer, { legacy: 'reject' });
const nodeHandler = toNodeHandler(mcp);
app.all('/mcp', auth, (req, res) => void nodeHandler(req, res, req.body));

let mcpClient;
app.get('/console', auth, async (_req, res, next) => {
  try {
    assert.ok(mcpClient, 'mcp_client_ready');
    const listed = await mcpClient.listTools();
    assert.deepEqual(listed.tools.map(tool => tool.name), TOOLS);
    for (const tool of listed.tools) {
      assert.equal(tool.annotations?.readOnlyHint, true);
      assert.equal(tool.annotations?.destructiveHint, false);
    }

    const current = await mcpClient.callTool({ name: 'context.current', arguments: {} });
    const status = await mcpClient.callTool({ name: 'context.status', arguments: {} });
    assert.notEqual(current.isError, true);
    assert.notEqual(status.isError, true);
    assert.equal(current.structuredContent?.mutation_allowed, false);
    assert.equal(status.structuredContent?.mutation_allowed, false);

    res.set({
      'Cache-Control': 'no-store, max-age=0',
      Pragma: 'no-cache',
      Expires: '0',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
      'Cross-Origin-Resource-Policy': 'same-origin',
    });
    res.type('html').send(renderConsole(current.structuredContent, status.structuredContent));
  } catch (error) {
    next(error);
  }
});

const httpServer = await new Promise((resolve, reject) => {
  const candidate = app.listen(0, '127.0.0.1', () => resolve(candidate));
  candidate.once('error', reject);
});
const address = httpServer.address();
assert.equal(typeof address, 'object');
assert.equal(address.address, '127.0.0.1');
assert.ok(address.port > 0);

const mcpEndpoint = new URL(`http://127.0.0.1:${address.port}/mcp`);
const consoleEndpoint = new URL(`http://127.0.0.1:${address.port}/console`);

async function fetchConsole(authorization, init = {}) {
  const headers = { ...(init.headers ?? {}) };
  if (authorization) headers.authorization = authorization;
  return fetch(consoleEndpoint, { ...init, headers });
}

try {
  const transport = new StreamableHTTPClientTransport(mcpEndpoint, {
    requestInit: { headers: { Authorization: `Bearer ${GOOD_TOKEN}` } },
  });
  mcpClient = new Client(
    { name: 'public-live-console-client', version: '1.0.0' },
    { versionNegotiation: { mode: { pin: PROTOCOL } } },
  );
  await mcpClient.connect(transport);
  assert.equal(mcpClient.getProtocolEra(), 'modern');

  const missing = await fetchConsole(undefined);
  assert.equal(missing.status, 401, 'missing token must be rejected');
  assert.match(missing.headers.get('www-authenticate') ?? '', /Bearer/i);

  const invalid = await fetchConsole('Bearer definitely-not-valid');
  assert.equal(invalid.status, 401, 'invalid token must be rejected');

  const noScope = await fetchConsole(`Bearer ${NO_SCOPE_TOKEN}`);
  assert.equal(noScope.status, 403, 'missing read scope must be rejected');

  const good = await fetchConsole(`Bearer ${GOOD_TOKEN}`);
  assert.equal(good.status, 200);
  assert.match(good.headers.get('content-type') ?? '', /^text\/html/i);
  assert.match(good.headers.get('cache-control') ?? '', /no-store/i);
  assert.equal(good.headers.get('etag'), null);
  assert.equal(good.headers.get('set-cookie'), null);
  assert.equal(good.headers.get('referrer-policy'), 'no-referrer');
  assert.match(good.headers.get('content-security-policy') ?? '', /default-src 'none'/);

  const html = await good.text();
  assert.match(html, /SYNTHETIC \/ READ ONLY \/ NON-AUTHORITATIVE/);
  assert.match(html, /Source: authenticated MCP transport only/);
  assert.match(html, /synthetic-current-context/);
  assert.equal(/<script\b/i.test(html), false, 'console has no script');
  assert.equal(/<form\b/i.test(html), false, 'console has no form');
  assert.equal(/<button\b/i.test(html), false, 'console has no button');
  assert.equal(/\bhref\s*=/i.test(html), false, 'console has no links');
  assert.equal(/\baction\s*=/i.test(html), false, 'console has no action endpoint');
  assert.equal(html.includes(GOOD_TOKEN), false, 'console must not expose bearer token');
  assert.equal(html.includes(NO_SCOPE_TOKEN), false, 'console must not expose no-scope token');

  const post = await fetchConsole(`Bearer ${GOOD_TOKEN}`, { method: 'POST' });
  assert.equal(post.status, 404, 'console exposes GET only');

  console.log('PUBLIC_CONTEXT_LIVE_CONSOLE_BIND=127.0.0.1');
  console.log('PUBLIC_CONTEXT_LIVE_CONSOLE_AUTH=401_401_403_PASS');
  console.log('PUBLIC_CONTEXT_LIVE_CONSOLE_SOURCE=MCP_ONLY');
  console.log('PUBLIC_CONTEXT_LIVE_CONSOLE_MCP_2026=PASS');
  console.log('PUBLIC_CONTEXT_LIVE_CONSOLE_CACHE=NO_STORE');
  console.log('PUBLIC_CONTEXT_LIVE_CONSOLE_INERT=PASS');
  console.log('PUBLIC_CONTEXT_LIVE_CONSOLE_GET_ONLY=PASS');
} finally {
  await mcpClient?.close().catch(() => {});
  await mcp.close().catch(() => {});
  await new Promise(resolve => httpServer.close(resolve));
}
