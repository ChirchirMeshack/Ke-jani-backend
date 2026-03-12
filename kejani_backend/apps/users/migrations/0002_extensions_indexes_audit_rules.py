"""
Data migration: PostgreSQL extensions, partial indexes, and audit log protection rules.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        # Enable uuid-ossp extension (for UUID generation)
        migrations.RunSQL(
            sql='CREATE EXTENSION IF NOT EXISTS "uuid-ossp";',
            reverse_sql='DROP EXTENSION IF EXISTS "uuid-ossp";',
        ),
        # Enable pg_trgm extension (for future listing search)
        migrations.RunSQL(
            sql='CREATE EXTENSION IF NOT EXISTS pg_trgm;',
            reverse_sql='DROP EXTENSION IF EXISTS pg_trgm;',
        ),
        # Partial index for login lookups — most frequent query
        migrations.RunSQL(
            sql=(
                'CREATE INDEX IF NOT EXISTS idx_users_email '
                'ON users (email) WHERE deleted_at IS NULL;'
            ),
            reverse_sql='DROP INDEX IF EXISTS idx_users_email;',
        ),
        # Audit log protection — prevent UPDATE and DELETE at DB level
        migrations.RunSQL(
            sql=(
                'CREATE OR REPLACE RULE no_update_audit '
                'AS ON UPDATE TO access_audit_log DO INSTEAD NOTHING;'
            ),
            reverse_sql='DROP RULE IF EXISTS no_update_audit ON access_audit_log;',
        ),
        migrations.RunSQL(
            sql=(
                'CREATE OR REPLACE RULE no_delete_audit '
                'AS ON DELETE TO access_audit_log DO INSTEAD NOTHING;'
            ),
            reverse_sql='DROP RULE IF EXISTS no_delete_audit ON access_audit_log;',
        ),
    ]
