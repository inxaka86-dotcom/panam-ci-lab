# Wave 5 — OpenResearch Workflow Graph mapper V1

Wave 5 validates the next pure projection layer:

`panam.openresearch.research-projection.v1 -> panam.workflow.graph.v1`.

The mapper does not read OpenResearch runtime state, does not call `orx`, and
does not create PANAM Task/Job State.

## Conservative mapping

- every experiment node has authority `NONE`;
- `answered` maps only to projected lifecycle state `completed`;
- `provisional` maps to `planned` even if the external run says `running`;
- no node maps to live `running` state;
- `runtime_observation.authoritative_runtime_bound=false`;
- `runtime_observation.active_nodes=[]`;
- result-claim text is omitted from the graph;
- only evidence pointers and the external claim-verification marker survive;
- sibling children become `fanout` edges; a sole child becomes `sequential`.

A green result is graph-projection evidence only.
