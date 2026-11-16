"""Synthetic Frappe-shaped user/query rules; no Frappe, SQL or real accounts."""
import types
import unittest
import test_treeview


def fixture(count):
    case = test_treeview.TreeTest(); case.setUp(); f = case.frappe
    f.session = types.SimpleNamespace(user='researcher')
    f.rows['Place'] = [{'name':'root','display_name':'Root','is_group':1,'parent_place':None}]
    f.rows['Place'] += [{'name':f'c{i:04}', 'display_name':f'Child {i}', 'is_group':0,
                         'parent_place':'root'} for i in range(count)]
    return case


def instrument(case, list_hidden=(), doc_denied=(), doctype_denied=False):
    f=case.frappe; original_list=f.get_list; original_permission=f.has_permission; original_exists=f.db.exists
    calls={'list_pages':0,'parent_lookup':0,'doctype_checks':0,'document_checks':0,'exists':0}
    def permission(doctype=None, ptype='read', doc=None, **kw):
        calls['document_checks' if doc is not None else 'doctype_checks'] += 1
        return not doctype_denied and doc not in doc_denied and original_permission(doctype,ptype,doc,**kw)
    def exists(dt,name):
        calls['exists']+=1
        return original_exists(dt,name)
    def get_list(dt, **kw):
        calls['parent_lookup' if 'name' in kw['filters'] else 'list_pages'] += 1
        # Model query conditions BEFORE paging; actual Frappe semantics are untested.
        saved=f.rows[dt]; f.rows[dt]=[row for row in saved if row['name'] not in list_hidden]
        try: return original_list(dt,**kw)
        finally: f.rows[dt]=saved
    f.has_permission=permission; f.db.exists=exists; f.get_list=get_list
    return calls


class PlaceTreeSyntheticTests(unittest.TestCase):
    def test_query_shape_root_and_parent_page_boundaries(self):
        for count in (0, 10, 200, 1000):
            with self.subTest(children=count):
                case=fixture(count); calls=instrument(case)
                result=case.tree.get_children('Place','root')
                self.assertEqual(len(result),count)
                self.assertEqual(calls['list_pages'],count//200+1)
                self.assertEqual(calls['parent_lookup'],1)
                self.assertEqual(calls['exists'],1)
                self.assertEqual(calls['document_checks'],count+1)
        case=fixture(10); calls=instrument(case)
        self.assertEqual([x['value'] for x in case.tree.get_children('Place')],['root'])
        self.assertEqual(calls['list_pages'],1); self.assertEqual(calls['parent_lookup'],0)
    def test_non_admin_owned_shared_list_and_document_denials(self):
        case=fixture(5)
        # c0000 models an owned record, c0001 a shared record; c0002 is hidden
        # by query conditions and c0003 is denied by a document-level hook.
        calls=instrument(case,list_hidden={'c0002'},doc_denied={'c0003'})
        rows=case.tree.get_children('Place','root')
        self.assertEqual([r['value'] for r in rows],['c0000','c0001','c0004'])
        self.assertEqual(calls['document_checks'],5)  # 4 listed children plus parent
    def test_user_specific_owner_share_and_custom_hook_model(self):
        case=fixture(4); f=case.frappe
        policy={
            'root': {'owner':'alice','shares':{'bob'}},
            'c0000': {'owner':'alice','shares':set()},
            'c0001': {'owner':'bob','shares':{'alice'}},
            'c0002': {'owner':'bob','shares':set()},
            'c0003': {'owner':'alice','shares':{'bob'}},
        }
        original_list=f.get_list
        def permission(doctype=None,ptype='read',doc=None,**kw):
            if doc is None: return True
            p=policy.get(doc)
            return bool(p and (p['owner']==f.session.user or f.session.user in p['shares']) and not (doc=='c0003' and f.session.user=='bob'))
        def list_query(dt, **kw):
            saved=f.rows[dt]
            # Document hook for bob/c0003 intentionally differs from list visibility.
            f.rows[dt]=[r for r in saved if (policy[r['name']]['owner']==f.session.user or f.session.user in policy[r['name']]['shares']) and not (r['name']=='c0002' and f.session.user=='bob')]
            try: return original_list(dt,**kw)
            finally: f.rows[dt]=saved
        f.has_permission=permission; f.get_list=list_query
        f.session.user='alice'
        self.assertEqual([r['value'] for r in case.tree.get_children('Place','root')],['c0000','c0001','c0003'])
        f.session.user='bob'
        self.assertEqual([r['value'] for r in case.tree.get_children('Place','root')],['c0001'])
        f.session.user='outsider'
        with self.assertRaises(PermissionError): case.tree.get_children('Place','root')

    def test_non_admin_hidden_parent_and_doctype_access_fail_closed(self):
        for opts in ({'list_hidden':{'root'}},{'doc_denied':{'root'}},{'doctype_denied':True}):
            with self.subTest(opts=opts):
                case=fixture(5); instrument(case,**opts)
                with self.assertRaises(PermissionError): case.tree.get_children('Place','root')
    def test_missing_parent_and_filtered_fields_are_not_disclosed(self):
        case=fixture(1); instrument(case); case.frappe.hidden_fields.add('display_name')
        self.assertEqual(case.tree.get_children('Place','root')[0]['title'],'c0000')
        with self.assertRaises(PermissionError): case.tree.get_children('Place','missing')

if __name__ == '__main__': unittest.main()
