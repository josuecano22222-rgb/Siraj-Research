"""Read-only, in-memory review of a supplied Event transition manifest.

No site inspection, schema writes or migration commands. Input and output may
contain sensitive metadata and identifiers; protect them and never commit them.
"""
from collections import Counter
from siraj_research.setup.event_schema_compare import compare_metadata
from siraj_research.setup.event_transition_plan import PlanError, prepare_transition

REVIEW_AREAS = ('physical_schema', 'custom_fields', 'property_setters', 'permissions', 'workflows',
                'scripts_hooks', 'reports_dashboards', 'integrations', 'external_references',
                'attachments', 'children', 'comments', 'audit_history', 'backup_restore')


def review(source_meta, target_meta, events, references, existing_target_names, coverage):
    """Report blockers in supplied fixture/manifest; cannot certify completeness.

    Coverage is the operator's claim, not independently verified. A zero-issue
    result never authorizes execution: an executor and actual rollback do not
    exist. The inputs are not mutated and no records or values are fetched.
    """
    issues = []
    if not isinstance(coverage, dict) or set(coverage) - set(REVIEW_AREAS):
        raise PlanError('Invalid coverage declaration')
    for name in REVIEW_AREAS:
        if coverage.get(name) != 'reviewed':
            issues.append({'kind':'coverage_unreviewed', 'area':name})
    comparison = compare_metadata(source_meta, target_meta)
    for row in comparison['mappings']:
        if row['status'] != 'same':
            issues.append({'kind':'field_' + row['status'], 'field':row['source'], 'differences':row['differences']})
    for name in comparison['target_only_fields']:
        issues.append({'kind':'target_only_field', 'field':name})
    for name in comparison['reserved_name_conflicts']:
        issues.append({'kind':'reserved_field', 'field':name})

    if not isinstance(events, list) or not isinstance(references, list) or not isinstance(existing_target_names, (list, tuple, set)):
        raise PlanError('Invalid manifest container')
    if any(not isinstance(x, str) or not x or x != x.strip() for x in existing_target_names):
        raise PlanError('Invalid target identity')
    target_names = set(existing_target_names)
    if not isinstance(existing_target_names, set):
        for name, count in sorted(Counter(existing_target_names).items()):
            if count > 1:
                issues.append({'kind':'duplicate_target', 'name':name, 'count':count})
    classes, names = {}, []
    for entry in events:
        if not isinstance(entry, dict) or set(entry) != {'name','classification'} or not isinstance(entry['name'], str) or not entry['name'] or entry['name'] != entry['name'].strip():
            raise PlanError('Invalid event entry')
        name, category = entry['name'], entry['classification']
        names.append(name)
        if category not in ('research','calendar'):
            issues.append({'kind':'event_unclassified', 'name':name})
        elif category == 'research' and name in target_names:
            issues.append({'kind':'target_name_conflict', 'name':name})
        if name not in classes:
            classes[name] = category
    for name, count in sorted(Counter(names).items()):
        if count > 1:
            issues.append({'kind':'duplicate_event', 'name':name, 'count':count})

    required = {'doctype','name','type_field','name_field','type_value','target','classification'}
    observed = set()
    for ref in references:
        if not isinstance(ref, dict) or set(ref) != required or any(not isinstance(ref[k], str) or not ref[k] or ref[k] != ref[k].strip() for k in required):
            raise PlanError('Invalid reference entry')
        identity = {'doctype':ref['doctype'], 'name':ref['name'], 'type_field':ref['type_field']}
        key = (ref['doctype'], ref['name'], ref['type_field'])
        if key in observed:
            issues.append({'kind':'duplicate_reference', **identity})
        observed.add(key)
        if ref['doctype'] in ('Event', 'SIRAJ Research Event'):
            issues.append({'kind':'event_owned_reference_unhandled', **identity})
        if ref['type_value'] != 'Event' or ref['type_field'] == ref['name_field']:
            issues.append({'kind':'unsupported_reference', **identity})
        if ref['target'] not in classes:
            issues.append({'kind':'orphan_reference', **identity})
        elif ref['classification'] not in ('research','calendar') or ref['classification'] != classes[ref['target']]:
            issues.append({'kind':'reference_classification_conflict', **identity})
    # Preserve the stricter planner's guards for overlaps and any other case.
    try:
        prepare_transition(events, references, existing_target_names)
    except PlanError as exc:
        issues.append({'kind':'planner_rejected', 'reason':str(exc)})
    return {'source':'Event', 'proposed_target':'SIRAJ Research Event',
            'schema':comparison, 'issues':issues,
            'input_counts':{'events':len(events), 'references':len(references), 'existing_targets':len(target_names)},
            'execution_ready':False,
            'warning':'Supplied metadata, coverage and classifications are unverified; no site or database was inspected or changed.'}
