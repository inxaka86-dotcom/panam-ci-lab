'use strict';

const fs = require('fs');
const path = require('path');

const {
  createRuntime,
  runOnce,
} = require('../wave10/runtime_entrypoint');

const storePath = process.argv[2];
const generationVariant = process.argv[3] || 'A';
const storeMode = process.argv[4] || 'ok';

if (!storePath) {
  process.stderr.write('store path required\n');
  process.exit(2);
}

function readRecords() {
  try {
    const parsed = JSON.parse(fs.readFileSync(storePath, 'utf8'));
    return Array.isArray(parsed.records) ? parsed.records : [];
  } catch (error) {
    if (error && error.code === 'ENOENT') return [];
    throw error;
  }
}

function writeRecords(records) {
  fs.mkdirSync(path.dirname(storePath), { recursive: true });
  const temp = `${storePath}.tmp-${process.pid}`;
  fs.writeFileSync(temp, JSON.stringify({ records }, null, 2) + '\n', { mode: 0o600 });
  fs.renameSync(temp, storePath);
}

function fileBackedStore() {
  return {
    async findByEventId(eventId) {
      return readRecords().filter(
        record => record.identity && record.identity.event_id === eventId
      );
    },

    async create(payload) {
      if (storeMode === 'fail') {
        throw new Error('synthetic storage failure');
      }
      const records = readRecords();
      const record = {
        id: `record-${records.length + 1}`,
        revision: `revision-${records.length + 1}`,
        name: payload.name,
        identity: payload.identity,
        stored_at: '2026-09-11T08:00:00Z',
      };
      records.push(record);
      writeRecords(records);
      return record;
    },
  };
}

const runtime = createRuntime({
  env: {
    SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE: 'wave11-protocol-scope',
  },
  providerLayerFactory: () => ({
    chat: async (_prompt, model) => ({
      text: `Synthetic protocol draft ${generationVariant}`,
      model: model || 'synthetic-model',
      provider: 'wave11-fixture',
    }),
  }),
  storeFactory: () => fileBackedStore(),
});

runOnce({
  input: process.stdin,
  output: process.stdout,
  runtime,
})
  .then(code => {
    process.exitCode = code;
  })
  .catch(error => {
    process.stderr.write(`fixture fatal: ${String(error && error.message || error)}\n`);
    process.exitCode = 1;
  });
