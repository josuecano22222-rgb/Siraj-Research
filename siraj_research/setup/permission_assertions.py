"""Opt-in isolated-site permission decision assertions; never whitelisted.

Uses existing accounts/records. No record creation, modification or deletion is
performed here. Permission hooks may have side effects and bench execute may
commit; only run after explicit isolated-site approval and hook review.
"""
from siraj_research.setup.permission_review import inspect_permissions, DOCTYPES, OPERATIONS, DOCUMENT_OPERATIONS


def check(cases, confirm=None):
    """Assert caller-supplied expected decisions using actual Frappe APIs.

    Each case has user, doctype, record_name and expect. `expect` may contain
    `doctype.<operation>`, `document.<operation>`, or `list_contains_record`.
    Output includes case indices and assertion names only, never names or rows.
    It checks permission decisions/list inclusion, not HTTP/CRUD enforcement.
    """
    if confirm != 'ISOLATED-TEST-APPROVED': raise ValueError('Explicit isolated test confirmation required')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 20: raise ValueError('Provide 1 to 20 cases')
    allowed = {'doctype.'+op for op in OPERATIONS} | {'document.'+op for op in DOCUMENT_OPERATIONS} | {'list_contains_record'}
    for case in cases:
        if not isinstance(case,dict) or set(case) != {'user','doctype','record_name','expect'}:
            raise ValueError('Invalid case')
        if not isinstance(case['user'],str) or not case['user'].strip() or case['user']=='Guest' or case['doctype'] not in DOCTYPES:
            raise ValueError('Invalid account or DocType')
        if not isinstance(case['record_name'],str) or not case['record_name'].strip(): raise ValueError('Existing record required')
        expect=case['expect']
        if not isinstance(expect,dict) or not expect or set(expect)-allowed or any(type(v) is not bool for v in expect.values()):
            raise ValueError('Invalid expectations')
    results=[]
    for index,case in enumerate(cases):
        info=inspect_permissions(case['user'],case['doctype'],case['record_name'])
        entry=info['doctypes'][case['doctype']]
        if entry.get('status') != 'checked': raise ValueError('DocType not checked')
        failures=[]
        for key, expected in case['expect'].items():
            if key.startswith('doctype.'): observed=entry['doctype_permissions'].get(key[8:])
            elif key.startswith('document.'): observed=entry['document_permissions'].get(key[9:])
            else: observed=entry.get('list_contains_record')
            if type(observed) is not bool or observed != expected: failures.append(key)
        results.append({'case_index':index,'assertions':len(case['expect']),'failures':sorted(failures),'passed':not failures})
    return {'cases':results, 'passed':all(x['passed'] for x in results),
            'note':'Decision/list assertions only; not direct API, actual CRUD, export or a security certification.'}
