'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const {
  createGenerationAdapter,
  createIdempotentArtifactWriter,
  sha256Text,
} = require('./runtime_adapter');

function req(overrides = {}) {
  const text = overrides.text || 'draft record';
  return {
    event_id: 'EVENT-1',
    document_type: 'meeting_record',
    storage_provider: 'synthetic_store',
    draft_id: 'DRAFT-1',
    artifact_id: 'ART-1',
    source_id: 'SOURCE-1',
    correlation_id: 'CORR-1',
    text_sha256: sha256Text(text),
    display_name: 'record.txt',
    ...overrides,
    text,
  };
}

function fakeStore(existing = []) {
  const calls = { find: [], create: [] };
  return {
    calls,
    store: {
      async findByEventId(eventId) {
        calls.find.push(eventId);
        return existing;
      },
      async create(input) {
        calls.create.push(input);
        return {
          id: 'STORE-NEW',
          revision: 'rev-1',
          name: input.name,
          stored_at: '2026-01-01T00:00:00Z',
          identity: input.identity,
        };
      },
    },
  };
}

test('generation adapter forwards exact operation', async () => {
  const calls = [];
  const generate = createGenerationAdapter({
    chat: async (...args) => {
      calls.push(args);
      return { text: 'draft', model: 'actual', provider: 'synthetic' };
    },
  });
  const out = await generate('prompt', 'requested', 'synthetic_protocol_generation');
  assert.deepEqual(calls, [['prompt', 'requested', 'synthetic_protocol_generation']]);
  assert.deepEqual(out, { text: 'draft', model: 'actual', provider: 'synthetic' });
});

test('generation adapter rejects wrong operation', async () => {
  const generate = createGenerationAdapter({ chat: async () => 'draft' });
  await assert.rejects(() => generate('prompt', null, 'other'), /unexpected/);
});

test('generation adapter rejects empty result', async () => {
  const generate = createGenerationAdapter({ chat: async () => '' });
  await assert.rejects(() => generate('prompt'), /empty/);
});

test('fresh write creates one artifact', async () => {
  const { store, calls } = fakeStore();
  const writer = createIdempotentArtifactWriter({ store });
  const request = req();
  const out = await writer(request, request.text);
  assert.equal(calls.create.length, 1);
  assert.equal(out.store_id, 'STORE-NEW');
  assert.equal(out.save_status, 'STORED');
  assert.equal(out.text_sha256, request.text_sha256);
});

test('exact replay reconstructs receipt without create', async () => {
  const request = req();
  const record = {
    id: 'STORE-EXISTING', revision: 'rev-9', name: 'record.txt',
    identity: {
      kind: 'synthetic_draft', event_id: request.event_id,
      draft_id: request.draft_id, artifact_id: request.artifact_id,
      text_sha256: request.text_sha256, source_id: request.source_id,
      correlation_id: request.correlation_id,
    },
  };
  const { store, calls } = fakeStore([record]);
  const writer = createIdempotentArtifactWriter({ store });
  const out = await writer(request, request.text);
  assert.equal(calls.create.length, 0);
  assert.equal(out.store_id, 'STORE-EXISTING');
  assert.equal(out.storage_revision, 'rev-9');
});

test('existing identity conflict fails closed', async () => {
  const request = req();
  const record = {
    id: 'STORE-EXISTING', revision: 'rev-1',
    identity: {
      kind: 'synthetic_draft', event_id: request.event_id,
      draft_id: 'OTHER', artifact_id: request.artifact_id,
      text_sha256: request.text_sha256, source_id: request.source_id,
      correlation_id: request.correlation_id,
    },
  };
  const { store, calls } = fakeStore([record]);
  const writer = createIdempotentArtifactWriter({ store });
  await assert.rejects(() => writer(request, request.text), /identity conflict/);
  assert.equal(calls.create.length, 0);
});

test('duplicate event artifacts fail closed', async () => {
  const request = req();
  const identity = {
    kind: 'synthetic_draft', event_id: request.event_id,
    draft_id: request.draft_id, artifact_id: request.artifact_id,
    text_sha256: request.text_sha256, source_id: request.source_id,
    correlation_id: request.correlation_id,
  };
  const { store, calls } = fakeStore([
    { id: 'A', revision: '1', identity },
    { id: 'B', revision: '1', identity },
  ]);
  const writer = createIdempotentArtifactWriter({ store });
  await assert.rejects(() => writer(request, request.text), /multiple/);
  assert.equal(calls.create.length, 0);
});

test('digest mismatch blocks store lookup and create', async () => {
  const { store, calls } = fakeStore();
  const writer = createIdempotentArtifactWriter({ store });
  const request = req({ text_sha256: '0'.repeat(64) });
  await assert.rejects(() => writer(request, request.text), /does not match/);
  assert.equal(calls.find.length, 0);
  assert.equal(calls.create.length, 0);
});

test('wrong document type blocks store I/O', async () => {
  const { store, calls } = fakeStore();
  const writer = createIdempotentArtifactWriter({ store });
  const request = req({ document_type: 'other' });
  await assert.rejects(() => writer(request, request.text), /document_type/);
  assert.equal(calls.find.length, 0);
});

test('wrong storage provider blocks store I/O', async () => {
  const { store, calls } = fakeStore();
  const writer = createIdempotentArtifactWriter({ store });
  const request = req({ storage_provider: 'other' });
  await assert.rejects(() => writer(request, request.text), /storage_provider/);
  assert.equal(calls.find.length, 0);
});

test('lineage key required before store I/O', async () => {
  const { store, calls } = fakeStore();
  const writer = createIdempotentArtifactWriter({ store });
  const request = req({ source_id: null, correlation_id: null });
  await assert.rejects(() => writer(request, request.text), /requires source_id/);
  assert.equal(calls.find.length, 0);
});

test('stored identity never contains raw text', async () => {
  const { store, calls } = fakeStore();
  const writer = createIdempotentArtifactWriter({ store });
  const request = req();
  await writer(request, request.text);
  assert.equal(Object.values(calls.create[0].identity).includes(request.text), false);
  assert.equal(calls.create[0].identity.text_sha256, request.text_sha256);
});

test('missing record revision fails closed', async () => {
  const request = req();
  const record = {
    id: 'STORE-EXISTING', revision: null,
    identity: {
      kind: 'synthetic_draft', event_id: request.event_id,
      draft_id: request.draft_id, artifact_id: request.artifact_id,
      text_sha256: request.text_sha256, source_id: request.source_id,
      correlation_id: request.correlation_id,
    },
  };
  const { store } = fakeStore([record]);
  const writer = createIdempotentArtifactWriter({ store });
  await assert.rejects(() => writer(request, request.text), /revision/);
});

test('store lookup contract must return array', async () => {
  const writer = createIdempotentArtifactWriter({
    store: {
      findByEventId: async () => null,
      create: async () => null,
    },
  });
  const request = req();
  await assert.rejects(() => writer(request, request.text), /return array/);
});
