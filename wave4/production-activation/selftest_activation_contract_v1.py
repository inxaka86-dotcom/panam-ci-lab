#!/usr/bin/env python3
from __future__ import annotations
import copy, json
from pathlib import Path
from urllib.parse import urlparse

C = json.loads((Path(__file__).with_name('activation_contract_v1.json')).read_text())

def blockers(c):
    out=[]; a=c['activation']; n=c['network']; o=c['oauth']; h=c['http']; l=c['logging']; au=c['authority']; d=c['data']; i=c['incident']
    u=urlparse(o['resource_identifier'])
    if not a['enabled']: out.append('activation_disabled')
    if a['owner_approval_required'] and not a['owner_approval_present']: out.append('owner_approval_missing')
    if a['ci_can_satisfy_owner_approval']: out.append('ci_authority_forbidden')
    if n['application_bind']!='127.0.0.1': out.append('application_not_loopback')
    if n['external_exposure']!='approved_tls_reverse_proxy_only': out.append('unapproved_exposure')
    if not n['https_required'] or n['minimum_tls']!='TLSv1.3': out.append('tls_policy')
    if u.scheme!='https' or not u.netloc or u.fragment: out.append('resource_identifier')
    if not o['protected_resource_metadata_required'] or o['protected_resource_metadata_path']!='/.well-known/oauth-protected-resource': out.append('resource_metadata')
    if not o['issuer_validation_required']: out.append('issuer_validation')
    if not o['resource_indicator_required'] or not o['audience_restricted_tokens_required']: out.append('audience_restriction')
    if o['allowed_scopes']!=['mcp:read']: out.append('scope_not_read_only')
    if o['bearer_transport']!=['authorization_header'] or o['query_token_allowed'] or o['cookie_token_allowed']: out.append('bearer_transport')
    if not 1 <= o['maximum_token_ttl_seconds'] <= 300: out.append('token_ttl')
    if not o['revocation_plan_required'] or not o['key_rotation_plan_required']: out.append('credential_lifecycle')
    if h['cache_control']!='no-store' or h['etag_allowed'] or h['cookies_allowed']: out.append('http_retention')
    if not h['hsts_required'] or not h['deny_by_default_csp_required']: out.append('http_hardening')
    if any((l['authorization_header_allowed'],l['request_body_allowed'],l['response_body_allowed'],l['plaintext_context_allowed'])) or not l['metadata_only']: out.append('sensitive_logging')
    if not au['read_only'] or au['mutation_allowed'] or au['owner_only_satisfied_by_ci'] or au['control_plane_bypass']: out.append('authority')
    if d['direct_memory_access'] or d['direct_database_access'] or d['direct_keyring_access'] or d['source']!='reviewed_context_projection_only' or d['durable_console_snapshot']: out.append('data_boundary')
    if not all(i.values()): out.append('incident_controls')
    return out

checks={
 'schema':C['schema']=='public.production-activation-contract.v1',
 'design_only':C['mode']=='design_only',
 'default_blocked':blockers(C)==['activation_disabled','owner_approval_missing'],
 'ci_not_owner':not C['activation']['ci_can_satisfy_owner_approval'],
 'loopback':C['network']['application_bind']=='127.0.0.1',
 'https_resource':C['oauth']['resource_identifier'].startswith('https://'),
 'resource_metadata':C['oauth']['protected_resource_metadata_path']=='/.well-known/oauth-protected-resource',
 'issuer_validation':C['oauth']['issuer_validation_required'],
 'audience':C['oauth']['resource_indicator_required'] and C['oauth']['audience_restricted_tokens_required'],
 'scope_exact':C['oauth']['allowed_scopes']==['mcp:read'],
 'auth_header_only':C['oauth']['bearer_transport']==['authorization_header'],
 'short_ttl':C['oauth']['maximum_token_ttl_seconds']<=300,
 'no_cache':C['http']['cache_control']=='no-store' and not C['http']['etag_allowed'] and not C['http']['cookies_allowed'],
 'metadata_logs_only':C['logging']['metadata_only'] and not C['logging']['plaintext_context_allowed'],
 'read_only':C['authority']['read_only'] and not C['authority']['mutation_allowed'],
 'projection_only':C['data']['source']=='reviewed_context_projection_only',
 'no_direct_stores':not C['data']['direct_memory_access'] and not C['data']['direct_database_access'] and not C['data']['direct_keyring_access'],
 'no_durable_console':not C['data']['durable_console_snapshot'],
 'incident_controls':all(C['incident'].values()),
}
ready=copy.deepcopy(C); ready['activation']['enabled']=True; ready['activation']['owner_approval_present']=True
checks['synthetic_ready']=blockers(ready)==[]
for section,key,value,expected in [
 ('authority','mutation_allowed',True,'authority'),
 ('oauth','allowed_scopes',['mcp:read','mcp:write'],'scope_not_read_only'),
 ('network','application_bind','0.0.0.0','application_not_loopback'),
 ('logging','request_body_allowed',True,'sensitive_logging')]:
    bad=copy.deepcopy(ready); bad[section][key]=value
    checks['reject_'+expected]=expected in blockers(bad)
failed=[k for k,v in checks.items() if not v]
if failed: raise SystemExit('PUBLIC_CONTEXT_PRODUCTION_ACTIVATION_CONTRACT_V1=FAIL '+','.join(failed))
print(f'PUBLIC_CONTEXT_PRODUCTION_ACTIVATION_CONTRACT_V1={len(checks)}/{len(checks)}_PASS')
print('PUBLIC_CONTEXT_PRODUCTION_ACTIVATION_DEFAULT_STATE=BLOCKED')
