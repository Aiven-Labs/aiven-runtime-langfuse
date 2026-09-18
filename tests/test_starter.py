import base64
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from bootstrap import prepare
from patch_migrations import patch


class StarterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certdir = tempfile.TemporaryDirectory()
        root = Path(cls.certdir.name)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(root/'key.pem'), '-out', str(root/'ca.pem'),
                        '-days', '1', '-subj', '/CN=Starter Test CA'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.pem = (root/'ca.pem').read_text()
        cls.ca = base64.b64encode(cls.pem.encode()).decode()

    @classmethod
    def tearDownClass(cls):
        cls.certdir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'startup'
        self.env = {
            'DATABASE_URL': 'postgres://demo:p%40ssword@pg.example.com:5432/defaultdb?sslmode=disable&host=wrong',
            'VALKEY_URL': 'rediss://default:p%26ssword@vk.example.com:6379/0?tls=false',
            'AIVEN_CA_CERT_BASE64': self.ca,
            'SALT': 'a'*64, 'ENCRYPTION_KEY': 'b'*64, 'NEXTAUTH_SECRET': 'c'*64,
            'NEXTAUTH_URL': 'https://web.example.com',
            'LANGFUSE_INIT_ORG_ID': 'org', 'LANGFUSE_INIT_PROJECT_ID': 'project',
            'LANGFUSE_INIT_USER_EMAIL': 'demo@example.com', 'LANGFUSE_INIT_USER_PASSWORD': 'test-password-long-enough',
            'CLICKHOUSE_URL': 'https://ch.example.com:8443',
            'CLICKHOUSE_MIGRATION_URL': 'clickhouse://ch.example.com:9440',
            'CLICKHOUSE_USER': 'demo', 'CLICKHOUSE_PASSWORD': 'p&ss+?#word', 'CLICKHOUSE_DB': 'langfuse',
            'S3_BUCKET': 'test-bucket', 'S3_REGION': 'auto',
            'S3_ENDPOINT': 'https://account.r2.cloudflarestorage.com',
            'S3_ACCESS_KEY_ID': 'test-id', 'S3_SECRET_ACCESS_KEY': 'test-secret',
        }

    def test_database_and_valkey_enforce_verified_tls(self):
        prepare(self.env, self.root, 'web')
        query = parse_qs(urlsplit(self.env['DATABASE_URL']).query)
        self.assertEqual(query['sslmode'], ['require'])
        self.assertEqual(query['sslaccept'], ['strict'])
        self.assertNotIn('host', query)
        self.assertEqual(self.env['DIRECT_URL'], self.env['DATABASE_URL'])
        self.assertEqual(self.env['REDIS_HOST'], 'vk.example.com')
        self.assertEqual(self.env['REDIS_AUTH'], 'p&ssword')
        self.assertEqual(self.env['REDIS_TLS_REJECT_UNAUTHORIZED'], 'true')
        self.assertEqual(self.env['REDIS_TLS_CHECK_SERVER_IDENTITY'], 'true')
        self.assertEqual(self.env['REDIS_TLS_SERVERNAME'], 'vk.example.com')
        self.assertEqual((self.root/'aiven-ca.pem').stat().st_mode & 0o777, 0o600)
        self.assertIn(self.pem, Path(self.env['SSL_CERT_FILE']).read_text())

    def test_migration_url_encodes_credentials_without_changing_http_password(self):
        prepare(self.env, self.root, 'web')
        query = parse_qs(urlsplit(self.env['STARTER_CLICKHOUSE_MIGRATION_URL']).query)
        self.assertEqual(query['password'], ['p&ss+?#word'])
        self.assertEqual(self.env['CLICKHOUSE_PASSWORD'], 'p&ss+?#word')
        self.assertEqual(self.env['CLICKHOUSE_MIGRATION_SSL'], 'true')
        self.assertEqual(self.env['CLICKHOUSE_CLUSTER_ENABLED'], 'false')

    def test_local_mode_explicitly_opts_out_for_local_services(self):
        self.env.update(LOCAL_DEVELOPMENT='true', NEXTAUTH_URL='http://localhost:8080', CLICKHOUSE_URL='http://clickhouse:8123')
        self.env.pop('AIVEN_CA_CERT_BASE64')
        prepare(self.env, self.root, 'web')
        self.assertEqual(parse_qs(urlsplit(self.env['DATABASE_URL']).query)['sslmode'], ['disable'])
        self.assertEqual(self.env['REDIS_TLS_ENABLED'], 'false')
        self.assertEqual(self.env['CLICKHOUSE_MIGRATION_SSL'], 'false')

    def test_missing_invalid_ca_and_insecure_origins_fail_closed(self):
        for key,value in [('AIVEN_CA_CERT_BASE64','bad!'), ('AIVEN_CA_CERT_BASE64',''),
                          ('NEXTAUTH_URL','http://example.com'), ('S3_ENDPOINT','http://storage.example.com'),
                          ('S3_ENDPOINT','https://u:secret@storage.example.com'),
                          ('CLICKHOUSE_URL','http://ch.example.com'),
                          ('CLICKHOUSE_MIGRATION_URL','clickhouse://ch.example.com:9440?skip_verify=true'),
                          ('NODE_TLS_REJECT_UNAUTHORIZED','0')]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    prepare(dict(self.env, **{key:value}), self.root, 'web')

    def test_bad_connection_errors_do_not_include_credentials(self):
        for value in ['postgres://user:private-password@[bad:5432/db', 'postgres://user:private-password@host:no/db']:
            with self.assertRaises(ValueError) as error:
                prepare(dict(self.env, DATABASE_URL=value), self.root, 'web')
            self.assertNotIn('private-password', str(error.exception))

    def test_s3_prefixes_and_private_initialization(self):
        prepare(self.env, self.root, 'web')
        self.assertEqual(self.env['AUTH_DISABLE_SIGNUP'], 'true')
        self.assertEqual(self.env['LANGFUSE_S3_EVENT_UPLOAD_PREFIX'], 'events/')
        self.assertEqual(self.env['LANGFUSE_S3_MEDIA_UPLOAD_PREFIX'], 'media/')
        self.assertEqual(self.env['LANGFUSE_S3_BATCH_EXPORT_ENABLED'], 'false')
        self.assertEqual(self.env['LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT'], self.env['S3_ENDPOINT'])

    def test_worker_does_not_require_web_credentials_and_binds_loopback(self):
        for key in list(self.env):
            if key.startswith('LANGFUSE_INIT_') or key=='NEXTAUTH_SECRET': self.env.pop(key)
        prepare(self.env, self.root, 'worker')
        self.assertEqual(self.env['HOSTNAME'], '127.0.0.1')
        self.assertEqual(self.env['PORT'], '3030')

    def test_secrets_and_bootstrap_account_are_required(self):
        for key,value in [('SALT','short'), ('ENCRYPTION_KEY','z'*64), ('NEXTAUTH_SECRET','a'*64),
                          ('LANGFUSE_INIT_USER_EMAIL','not-email'), ('LANGFUSE_INIT_USER_PASSWORD','short'),
                          ('LANGFUSE_INIT_PROJECT_ID',''), ('S3_SECRET_ACCESS_KEY','')]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    prepare(dict(self.env, **{key:value}), self.root, 'web')

    def test_tls_patch_rejects_unexpected_upstream_script(self):
        with self.assertRaises(ValueError): patch('changed upstream script')
        sample = 'DATABASE_URL="${CLICKHOUSE_MIGRATION_URL}?username=${CLICKHOUSE_USER}&password=${CLICKHOUSE_PASSWORD}&database=${CLICKHOUSE_DB}&x-multi-statement=true"\nDATABASE_URL="${DATABASE_URL}&secure=true&skip_verify=true"\n'
        fixed = patch(sample)
        self.assertIn('skip_verify=false', fixed)
        self.assertNotIn('skip_verify=true', fixed)
        self.assertIn('STARTER_CLICKHOUSE_MIGRATION_URL', fixed)
        with self.assertRaises(ValueError): patch(fixed)

    def test_synthetic_trace_has_valid_ids_timestamps_and_no_provider_call(self):
        path = Path(__file__).parents[1]/'examples/send_trace.py'
        spec=importlib.util.spec_from_file_location('example',path)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        data=mod.payload('a'*32,'b'*16,1000000)
        span=data['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
        self.assertEqual(span['traceId'],'a'*32)
        self.assertGreater(int(span['endTimeUnixNano']),int(span['startTimeUnixNano']))


if __name__ == '__main__':
    unittest.main()
