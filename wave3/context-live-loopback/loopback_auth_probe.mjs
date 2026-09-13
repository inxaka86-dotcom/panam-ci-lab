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
      return { token, clientId: 'public-loopback-probe', scopes: [REQUIRED_SCOPE], expiresAt };
    }
    if (token === NO_SCOPE_TOKEN) {
      return { token, clientId: 'public-loopback-probe-noscope', scopes: [], expiresAt };
    }
    throw new OAuthError(OAuthErrorCode.InvalidToken, 'unknown token');
  },
};

function buildServer() {
  const server = new McpServer(
    { name: 'public-context-loopback-probe', version: '1.0.0' },
    {
      capabilities: { tools: {} },
      instructions: 'Synthetic read-only loopback transport proof. No private data and no mutation.',
    },
  );

  const annotations = {
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: false,
  };

  for (const name of TOOLS) {
    server.registerTool(
      name,
      {
        description: `Synthetic read-only tool: ${name}`,
        inputSchema: z.object({}),
        annotations,
      },
      async (_args, ctx) => {
        const auth = ctx.http?.authInfo;
        assert.equal(auth?.clientId, 'public-loopback-probe');
        assert.equal(auth?.scopes.includes(REQUIRED_SCOPE), true);
        return {
          content: [{ type: 'text', text: JSON.stringify({ ok: true, tool: name }) }],
          structuredContent: {
            ok: true,
            tool: name,
            authoritative: false,
            mutation_allowed: false,
            authenticated: true,
          },
        };
      },
    );
  }

  return server;
}

const app = createMcpExpressApp({ host: '127.0.0.1', allowedHosts: ['127.0.0.1'] });
const auth = requireBearerAuth({ verifier, requiredScopes: [REQUIRED_SCOPE] });
const mcp = createMcpHandler(buildServer, { legacy: 'reject' });
const nodeHandler = toNodeHandler(mcp);
app.all('/mcp', auth, (req, res) => void nodeHandler(req, res, req.body));

const httpServer = await new Promise((resolve, reject) => {
  const candidate = app.listen(0, '127.0.0.1', () => resolve(candidate));
  candidate.once('error', reject);
});

const address = httpServer.address();
assert.equal(typeof address, 'object');
assert.equal(address.address, '127.0.0.1');
assert.ok(address.port > 0);
const endpoint = new URL(`http://127.0.0.1:${address.port}/mcp`);

async function rawAuthStatus(authorization) {
  const headers = { 'content-type': 'application/json' };
  if (authorization) headers.authorization = authorization;
  return fetch(endpoint, {
    method: 'POST',
    headers,
    body: '{}',
  });
}

let client;
try {
  const missing = await rawAuthStatus(undefined);
  assert.equal(missing.status, 401, 'missing token must be rejected');
  assert.match(missing.headers.get('www-authenticate') ?? '', /Bearer/i);

  const invalid = await rawAuthStatus('Bearer definitely-not-valid');
  assert.equal(invalid.status, 401, 'invalid token must be rejected');

  const noScope = await rawAuthStatus(`Bearer ${NO_SCOPE_TOKEN}`);
  assert.equal(noScope.status, 403, 'missing read scope must be rejected');

  const transport = new StreamableHTTPClientTransport(endpoint, {
    requestInit: { headers: { Authorization: `Bearer ${GOOD_TOKEN}` } },
  });
  client = new Client(
    { name: 'public-context-loopback-client', version: '1.0.0' },
    { versionNegotiation: { mode: { pin: PROTOCOL } } },
  );

  await client.connect(transport);
  assert.equal(client.getProtocolEra(), 'modern');

  const listed = await client.listTools();
  assert.deepEqual(listed.tools.map(tool => tool.name), TOOLS);
  for (const tool of listed.tools) {
    assert.equal(tool.annotations?.readOnlyHint, true);
    assert.equal(tool.annotations?.destructiveHint, false);
  }

  for (const name of TOOLS) {
    const result = await client.callTool({ name, arguments: {} });
    assert.equal(result.isError, undefined);
    assert.deepEqual(result.structuredContent, {
      ok: true,
      tool: name,
      authoritative: false,
      mutation_allowed: false,
      authenticated: true,
    });
  }

  console.log('PUBLIC_CONTEXT_LOOPBACK_BIND=127.0.0.1');
  console.log('PUBLIC_CONTEXT_LOOPBACK_AUTH=401_401_403_PASS');
  console.log('PUBLIC_CONTEXT_LOOPBACK_MCP_2026=PASS');
  console.log('PUBLIC_CONTEXT_LOOPBACK_READ_ONLY=PASS');
} finally {
  await client?.close().catch(() => {});
  await mcp.close().catch(() => {});
  await new Promise(resolve => httpServer.close(resolve));
}
