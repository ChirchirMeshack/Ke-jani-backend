from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('properties', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql='''
            CREATE OR REPLACE VIEW v_unit_tenant_summary AS
            SELECT
                u.id          AS unit_id,
                u.unit_number,
                u.status,
                u.rent_amount,
                p.id          AS property_id,
                p.name        AS property_name,
                p.county,
                l.id          AS landlord_id,
                lu.email      AS landlord_email,
                lu.first_name AS landlord_first_name
            FROM units u
            JOIN properties p  ON p.id = u.property_id
            JOIN landlords l   ON l.id = p.landlord_id
            JOIN users lu      ON lu.id = l.user_id
            WHERE u.deleted_at IS NULL
              AND p.deleted_at IS NULL;
            ''',
            reverse_sql='DROP VIEW IF EXISTS v_unit_tenant_summary;',
        ),
    ]
