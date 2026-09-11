# Wave 8: public synthetic runtime adapter

Wave 8 validates the generic runtime edge needed after Wave 7:

`generation callable -> normalized generated text -> idempotent external artifact writer -> Wave 6-compatible receipt`

## Contract

- the generation adapter forwards one bounded generation operation and rejects malformed/empty output;
- the artifact writer validates exact text digest, document type, storage provider and lineage key before external-store I/O;
- writer-side `event_id` idempotency closes the crash window before the local Wave 6 checkpoint;
- zero event matches creates one artifact;
- one exact identity match reconstructs the receipt without another create;
- one conflicting match or multiple event matches fails closed;
- identity metadata stores hashes/IDs only, never raw transcript or draft text;
- a stable record ID and revision are required before a `STORED` receipt can be trusted.

Everything in this public wave uses a fake chat callable and in-memory synthetic store. There is no private repository access, external service, real Drive, credential, secret, production sending, watcher or deployment authority.

The public mirror validates the generic runtime/idempotency contract only. It does not expose or authorize PANAM's private runtime wiring.
