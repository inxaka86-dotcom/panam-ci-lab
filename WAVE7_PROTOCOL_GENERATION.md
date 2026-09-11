# Wave 7: public synthetic protocol generation feedback loop

Wave 7 validates a public-safe generation path:

`ACCEPTED reusable rule -> deterministic generation context -> synthetic generator -> Wave 6 -> Wave 5 -> Wave 4 -> Wave 3`

## Contract

- only `ACCEPTED` reusable rules may enter generation context;
- accepted rules are revalidated for learnable category, manual verification, >=3 evidence pairs, zero contradictions and intact acceptance-policy guards;
- substantive/legal corrections fail closed;
- candidate rules are ignored;
- transcript content is explicitly treated as data, not instructions;
- prompt generation forbids inventing facts, deadlines, legal grounds, names, decisions or responsibilities;
- generation receipts persist hashes/IDs only, never raw transcript or raw generated text;
- generated draft hash is the exact identity handed to Wave 6;
- generator failure occurs before any storage writer call;
- full-chain validation must reach Wave 3 `READY_FOR_CHANGE_REVIEW` while changes remain `UNCLASSIFIED_REQUIRES_REVIEW`.

All identifiers, text, storage IDs and providers in this public wave are synthetic. There is no private repository access, real Drive access, secret, credential, production deployment, sending authority, watcher or Autopilot activation.

A passing public workflow is engineering evidence only.
