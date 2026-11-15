"""Independent content identity and compatibility with old schema1 releases."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from create_module_assets import resource_revision,native_revision,package_resources,validate_catalog
from test_module_release import ModuleReleaseTest
class RevisionTest(unittest.TestCase):
    def test_resource_identity_survives_repack_and_version_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';(source/'payload').mkdir(parents=True);art=source/'payload/art.png';art.write_bytes(b'original')
            revision=resource_revision(source)
            # This is the exact byte protocol used by the Java client.
            expected=hashlib.sha256(b'ACM-MODULE-ASSETS/1\n'+b'art.png\0'+b'8\0'+hashlib.sha256(b'original').hexdigest().encode()+b'\n').hexdigest()
            self.assertEqual(revision,'a1-'+expected)
            for code in (41,42):
                pack=Path(tmp)/f'{code}.zip';package_resources(source,pack,'cat-art',code)
                with ZipFile(pack) as z:self.assertEqual(json.loads(z.read('module.json'))['revision'],revision)
            art.write_bytes(b'changed!');self.assertNotEqual(resource_revision(source),revision)
    def test_path_order_is_ordinal_posix_not_pathlib_or_windows_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);payload=root/'payload';payload.mkdir()
            values={'b/a.txt':b'A','b-x.txt':b'B','Z.txt':b'C','a.txt':b'D'}
            for name,content in values.items():
                path=payload/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
            digest=hashlib.sha256(b'ACM-MODULE-ASSETS/1\n')
            for name in sorted(values):
                content=values[name];digest.update((name+'\0'+str(len(content))+'\0'+hashlib.sha256(content).hexdigest()+'\n').encode())
            self.assertEqual(resource_revision(root),'a1-'+digest.hexdigest())
    def test_native_revision_tracks_code_not_build_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'src/main').mkdir(parents=True);(p/'build.gradle').write_text('feature');(p/'src/main/X.java').write_text('code')
            revision=native_revision(p);(p/'build').mkdir();(p/'build/output.apk').write_bytes(b'output');self.assertEqual(native_revision(p),revision)
            (p/'src/main/X.java').write_text('changed');self.assertNotEqual(native_revision(p),revision)
class RevisedReleaseTest(ModuleReleaseTest):
    def setUp(self):
        super().setUp()
        for row in self.catalog['modules']:row['revision']=('n1-' if row['kind']=='native' else 'a1-')+'a'*64
        self.save()
    def test_invalid_revision_rejected_before_upload(self):
        for value in (None,123,'broken','n1-'+'a'*64):
            with self.subTest(value=value):
                self.catalog['modules'][0]['revision']=value;self.save()
                with self.assertRaises(ValueError):self.publish()
                self.assertEqual(self.github.operations,[])
