'use strict';

const {
  createGenerationAdapter,
  createIdempotentArtifactWriter,
} = require('../wave8/runtime_adapter');
const {
  runJsonWorkerOnce,
  safeErrorMessage,
} = require('../wave9/protocol_runtime_worker');

function nonempty(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function createRuntime({
  env = {},
  providerLayerFactory,
  storeFactory,
} = {}) {
  let generator = null;
  let writer = null;

  function getGenerator() {
    if (generator) return generator;
    if (typeof providerLayerFactory !== 'function') {
      throw new Error('synthetic provider layer is unavailable');
    }
    const layer = providerLayerFactory();
    if (!layer || typeof layer.chat !== 'function') {
      throw new Error('synthetic provider layer did not expose chat()');
    }
    generator = createGenerationAdapter({ chat: layer.chat });
    return generator;
  }

  function getWriter() {
    if (writer) return writer;
    const scope = env.SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE;
    if (!nonempty(scope)) {
      throw new Error('SYNTHETIC_PROTOCOL_ARTIFACT_SCOPE is required');
    }
    if (typeof storeFactory !== 'function') {
      throw new Error('synthetic store factory is unavailable');
    }
    const store = storeFactory(scope);
    writer = createIdempotentArtifactWriter({ store });
    return writer;
  }

  return Object.freeze({
    generator: async (...args) => getGenerator()(...args),
    writer: async (...args) => getWriter()(...args),
  });
}

async function runOnce({
  input,
  output,
  runtime = null,
  runtimeOptions = {},
} = {}) {
  const active = runtime || createRuntime(runtimeOptions);
  return runJsonWorkerOnce({
    input,
    output,
    generator: active.generator,
    writer: active.writer,
  });
}

if (require.main === module) {
  runOnce({
    input: process.stdin,
    output: process.stdout,
  })
    .then(code => {
      process.exitCode = code;
    })
    .catch(error => {
      process.stderr.write(`synthetic runtime fatal: ${safeErrorMessage(error)}\n`);
      process.exitCode = 1;
    });
}

module.exports = {
  createRuntime,
  runOnce,
};
