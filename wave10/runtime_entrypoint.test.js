'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { PassThrough } = require('stream');

const {
  DOCUMENT_TYPE,
  STORAGE_PROVIDER,
  GENERATION_OPERATION,
  sha256Text,
} = require('../wave8/runtime_adapter');
const {
  createRuntime,
  runOnce,
} = require('./runtime_entrypoint');

function requestFor(text = 'draft') {
  return {
    event_id: 'event-1',
    document_type: DOCUMENT_TYPE,
    storage_provider: STORAGE_PROVIDER,
    draft_id: 'draft-1',
    artifact_id: 'artifact-1',
    text_sha256: sha256Text(text),
    source_id: 'source-1',
    correlation_id: 'corr-1',
    display_name: 'protocol.txt',
  };
}

function freshStore() {
  const records = [];
  let creates = 0;
  return {
    get creates() {
      return creates;
    },
    records,
    async findByEventId(eventId) {
      return records.filter(
        item => item.identity.event_id === eventId
      );
    },
    async create(payload) {
      creates += 1;
      const record = {
        id: `record-${creates}`,
        revision: `revision-${creates}`,
        name: payload.name,
        identity: payload.identity,
        stored_at: '2026-09-11T07:00:00Z',
      };
      records.push(record);
      return record;
    },
  };
}

test('generation is lazy and does not construct store', async () => {
  let providerCalls = 0;
  let storeCalls = 0;
  const runtime = createRuntime({
    env: {
      SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE: 'protocol-scope',
    },
    providerLayerFactory: () => {
      providerCalls += 1;
      return {
        chat: async (prompt, model, operation) => ({
          text: `draft:${prompt}`,
          model,
          provider: 'synthetic-provider',
          operation,
        }),
      };
    },
    storeFactory: () => {
      storeCalls += 1;
      return freshStore();
    },
  });

  const result = await runtime.generator(
    'hello',
    'synthetic-model',
    GENERATION_OPERATION
  );

  assert.equal(result.text, 'draft:hello');
  assert.equal(providerCalls, 1);
  assert.equal(storeCalls, 0);
});

test('generation fails closed when provider layer is unavailable', async () => {
  const runtime = createRuntime({
    env: {
      SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE: 'protocol-scope',
    },
  });

  await assert.rejects(
    () => runtime.generator(
      'hello',
      'synthetic-model',
      GENERATION_OPERATION
    ),
    /provider layer is unavailable/
  );
});

test('store requires dedicated protocol scope and never falls back to generic scope', async () => {
  let storeCalls = 0;
  const runtime = createRuntime({
    env: {
      GENERIC_ARTIFACT_SCOPE: 'generic-inbox-scope',
    },
    providerLayerFactory: () => ({
      chat: async () => ({ text: 'unused' }),
    }),
    storeFactory: () => {
      storeCalls += 1;
      return freshStore();
    },
  });

  await assert.rejects(
    () => runtime.writer(
      requestFor(),
      'draft'
    ),
    /SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE is required/
  );

  assert.equal(storeCalls, 0);
});

test('store passes only the dedicated protocol scope to the real Wave 8 writer', async () => {
  let scopeSeen = null;
  const store = freshStore();
  const runtime = createRuntime({
    env: {
      GENERIC_ARTIFACT_SCOPE: 'generic-inbox-scope',
      SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE: 'protocol-scope',
    },
    providerLayerFactory: () => ({
      chat: async () => ({ text: 'unused' }),
    }),
    storeFactory: scope => {
      scopeSeen = scope;
      return store;
    },
  });

  const result = await runtime.writer(
    requestFor(),
    'draft'
  );

  assert.equal(scopeSeen, 'protocol-scope');
  assert.equal(result.save_status, 'STORED');
  assert.equal(store.creates, 1);
});

test('exact store replay uses real Wave 8 idempotency without another create', async () => {
  const store = freshStore();
  const runtime = createRuntime({
    env: {
      SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE: 'protocol-scope',
    },
    providerLayerFactory: () => ({
      chat: async () => ({ text: 'unused' }),
    }),
    storeFactory: () => store,
  });

  const request = requestFor();
  const first = await runtime.writer(request, 'draft');
  const second = await runtime.writer(request, 'draft');

  assert.equal(store.creates, 1);
  assert.equal(first.store_id, second.store_id);
  assert.equal(
    first.storage_revision,
    second.storage_revision
  );
});

test('one-shot Wave 9 worker reaches real Wave 8 generation adapter', async () => {
  const input = new PassThrough();
  const output = new PassThrough();
  let raw = '';

  output.on('data', chunk => {
    raw += chunk.toString();
  });

  const runtime = createRuntime({
    env: {
      SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE: 'protocol-scope',
    },
    providerLayerFactory: () => ({
      chat: async prompt => ({
        text: `generated:${prompt}`,
        model: 'synthetic-model',
        provider: 'synthetic-provider',
      }),
    }),
    storeFactory: () => freshStore(),
  });

  input.end(
    JSON.stringify({
      schema_version: 1,
      operation: 'generate',
      payload: {
        prompt: 'prompt',
        model: 'synthetic-model',
        generation_operation: GENERATION_OPERATION,
      },
    })
  );

  const code = await runOnce({
    input,
    output,
    runtime,
  });

  assert.equal(code, 0);
  const response = JSON.parse(raw.trim());
  assert.equal(response.ok, true);
  assert.equal(response.result.text, 'generated:prompt');
});

test('one-shot Wave 9 worker reaches real Wave 8 writer', async () => {
  const input = new PassThrough();
  const output = new PassThrough();
  let raw = '';
  const store = freshStore();

  output.on('data', chunk => {
    raw += chunk.toString();
  });

  const runtime = createRuntime({
    env: {
      SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE: 'protocol-scope',
    },
    providerLayerFactory: () => ({
      chat: async () => ({ text: 'unused' }),
    }),
    storeFactory: () => store,
  });

  input.end(
    JSON.stringify({
      schema_version: 1,
      operation: 'store',
      payload: {
        request: requestFor(),
        text: 'draft',
      },
    })
  );

  const code = await runOnce({
    input,
    output,
    runtime,
  });

  assert.equal(code, 0);
  const response = JSON.parse(raw.trim());
  assert.equal(response.ok, true);
  assert.equal(response.result.save_status, 'STORED');
  assert.equal(store.creates, 1);
});

test('provider and store remain independent lazy dependencies', async () => {
  let providerCalls = 0;
  let storeCalls = 0;
  const store = freshStore();
  const runtime = createRuntime({
    env: {
      SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE: 'protocol-scope',
    },
    providerLayerFactory: () => {
      providerCalls += 1;
      return {
        chat: async () => ({
          text: 'draft',
          model: 'synthetic-model',
          provider: 'synthetic-provider',
        }),
      };
    },
    storeFactory: () => {
      storeCalls += 1;
      return store;
    },
  });

  await runtime.writer(
    requestFor(),
    'draft'
  );
  assert.equal(providerCalls, 0);
  assert.equal(storeCalls, 1);

  await runtime.generator(
    'prompt',
    'synthetic-model',
    GENERATION_OPERATION
  );
  assert.equal(providerCalls, 1);
  assert.equal(storeCalls, 1);
});
