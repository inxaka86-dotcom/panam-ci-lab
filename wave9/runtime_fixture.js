'use strict';

const { createGenerationAdapter, createIdempotentArtifactWriter } = require('../wave8/runtime_adapter');
const { runJsonWorkerOnce } = require('./protocol_runtime_worker');

const generator = createGenerationAdapter({
  chat: async (prompt, model, operation) => ({
    text: `DRAFT:${prompt.slice(0, 20)}`,
    model: model || 'synthetic-model',
    provider: 'synthetic-provider',
    operation,
  }),
});

const records = [];
const writer = createIdempotentArtifactWriter({
  store: {
    async findByEventId(eventId) {
      return records.filter(item => item.identity.event_id === eventId);
    },
    async create(input) {
      const record = {
        id: `STORE-${records.length + 1}`,
        revision: `rev-${records.length + 1}`,
        name: input.name,
        stored_at: '2026-01-01T00:00:00Z',
        identity: input.identity,
      };
      records.push(record);
      return record;
    },
  },
});

runJsonWorkerOnce({
  input: process.stdin,
  output: process.stdout,
  generator,
  writer,
}).then(code => {
  process.exitCode = code;
});
