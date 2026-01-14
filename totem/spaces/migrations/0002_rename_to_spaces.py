from django.db import migrations


def rename_circles_to_spaces(apps, schema_editor):
    """Rename circles app to spaces with all tables, columns, constraints, and indexes.

    This migration is only needed for existing databases that have the old 'circles_*' tables.
    Fresh installs will create 'spaces_*' tables directly and skip the rename operations.
    """
    with schema_editor.connection.cursor() as cursor:
        # Check if the new tables already exist (fresh installs will have them)
        cursor.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'spaces_space');"
        )
        new_tables_exist = cursor.fetchone()[0]

        if new_tables_exist:
            # Fresh install - tables were already created with new names by 0001_initial
            return

        # =====================================================
        # PHASE 1: Update django_content_type (CRITICAL FIRST)
        # This preserves taggit tags, auditlog, permissions
        # =====================================================
        cursor.execute("UPDATE django_content_type SET app_label = 'spaces' WHERE app_label = 'circles';")
        cursor.execute(
            "UPDATE django_content_type SET model = 'space' WHERE app_label = 'spaces' AND model = 'circle';"
        )
        cursor.execute(
            "UPDATE django_content_type SET model = 'session' WHERE app_label = 'spaces' AND model = 'circleevent';"
        )
        cursor.execute(
            "UPDATE django_content_type SET model = 'spacecategory' WHERE app_label = 'spaces' AND model = 'circlecategory';"
        )

        # =====================================================
        # PHASE 2: Update django_migrations
        # =====================================================
        cursor.execute("UPDATE django_migrations SET app = 'spaces' WHERE app = 'circles';")

        # =====================================================
        # PHASE 3: Drop FK constraints (to allow renames)
        # =====================================================
        cursor.execute("ALTER TABLE circles_circle DROP CONSTRAINT circles_circle_author_id_3be3d6f7_fk_users_user_id;")
        cursor.execute(
            "ALTER TABLE circles_circleevent DROP CONSTRAINT circles_circleevent_circle_id_816ee437_fk_circles_circle_id;"
        )
        cursor.execute(
            "ALTER TABLE circles_sessionfeedback DROP CONSTRAINT circles_sessionfeedb_event_id_b0305c8d_fk_circles_c;"
        )
        cursor.execute(
            "ALTER TABLE circles_sessionfeedback DROP CONSTRAINT circles_sessionfeedback_user_id_88d17eec_fk_users_user_id;"
        )
        cursor.execute(
            "ALTER TABLE circles_circle_categories DROP CONSTRAINT circles_circle_categ_circle_id_8ef9be67_fk_circles_c;"
        )
        cursor.execute(
            "ALTER TABLE circles_circle_categories DROP CONSTRAINT circles_circle_categ_circlecategory_id_ab707200_fk_circles_c;"
        )
        cursor.execute(
            "ALTER TABLE circles_circle_subscribed DROP CONSTRAINT circles_circle_subsc_circle_id_3da57f69_fk_circles_c;"
        )
        cursor.execute(
            "ALTER TABLE circles_circle_subscribed DROP CONSTRAINT circles_circle_subscribed_user_id_99082b2c_fk_users_user_id;"
        )
        cursor.execute(
            "ALTER TABLE circles_circleevent_attendees DROP CONSTRAINT circles_circleevent__circleevent_id_324eacfb_fk_circles_c;"
        )
        cursor.execute(
            "ALTER TABLE circles_circleevent_attendees DROP CONSTRAINT circles_circleevent_attendees_user_id_c0299166_fk_users_user_id;"
        )
        cursor.execute(
            "ALTER TABLE circles_circleevent_joined DROP CONSTRAINT circles_circleevent__circleevent_id_a7966a11_fk_circles_c;"
        )
        cursor.execute(
            "ALTER TABLE circles_circleevent_joined DROP CONSTRAINT circles_circleevent_joined_user_id_38fe1c26_fk_users_user_id;"
        )

        # =====================================================
        # PHASE 4: Rename columns in child tables FIRST
        # =====================================================
        cursor.execute("ALTER TABLE circles_circleevent RENAME COLUMN circle_id TO space_id;")
        cursor.execute("ALTER TABLE circles_sessionfeedback RENAME COLUMN event_id TO session_id;")
        cursor.execute("ALTER TABLE circles_circle_categories RENAME COLUMN circle_id TO space_id;")
        cursor.execute("ALTER TABLE circles_circle_categories RENAME COLUMN circlecategory_id TO spacecategory_id;")
        cursor.execute("ALTER TABLE circles_circle_subscribed RENAME COLUMN circle_id TO space_id;")
        cursor.execute("ALTER TABLE circles_circleevent_attendees RENAME COLUMN circleevent_id TO session_id;")
        cursor.execute("ALTER TABLE circles_circleevent_joined RENAME COLUMN circleevent_id TO session_id;")

        # =====================================================
        # PHASE 5: Rename tables
        # =====================================================
        cursor.execute("ALTER TABLE circles_circlecategory RENAME TO spaces_spacecategory;")
        cursor.execute("ALTER TABLE circles_circle RENAME TO spaces_space;")
        cursor.execute("ALTER TABLE circles_circleevent RENAME TO spaces_session;")
        cursor.execute("ALTER TABLE circles_sessionfeedback RENAME TO spaces_sessionfeedback;")
        cursor.execute("ALTER TABLE circles_circle_categories RENAME TO spaces_space_categories;")
        cursor.execute("ALTER TABLE circles_circle_subscribed RENAME TO spaces_space_subscribed;")
        cursor.execute("ALTER TABLE circles_circleevent_attendees RENAME TO spaces_session_attendees;")
        cursor.execute("ALTER TABLE circles_circleevent_joined RENAME TO spaces_session_joined;")

        # =====================================================
        # PHASE 6: Rename sequences
        # =====================================================
        cursor.execute("ALTER SEQUENCE circles_circlecategory_id_seq RENAME TO spaces_spacecategory_id_seq;")
        cursor.execute("ALTER SEQUENCE circles_circle_id_seq RENAME TO spaces_space_id_seq;")
        cursor.execute("ALTER SEQUENCE circles_circleevent_id_seq RENAME TO spaces_session_id_seq;")
        cursor.execute("ALTER SEQUENCE circles_sessionfeedback_id_seq RENAME TO spaces_sessionfeedback_id_seq;")
        cursor.execute("ALTER SEQUENCE circles_circle_categories_id_seq RENAME TO spaces_space_categories_id_seq;")
        cursor.execute("ALTER SEQUENCE circles_circle_subscribed_id_seq RENAME TO spaces_space_subscribed_id_seq;")
        cursor.execute(
            "ALTER SEQUENCE circles_circleevent_attendees_id_seq RENAME TO spaces_session_attendees_id_seq;"
        )
        cursor.execute("ALTER SEQUENCE circles_circleevent_joined_id_seq RENAME TO spaces_session_joined_id_seq;")

        # =====================================================
        # PHASE 7: Rename primary key constraints
        # =====================================================
        cursor.execute(
            "ALTER TABLE spaces_spacecategory RENAME CONSTRAINT circles_circlecategory_pkey TO spaces_spacecategory_pkey;"
        )
        cursor.execute("ALTER TABLE spaces_space RENAME CONSTRAINT circles_circle_pkey TO spaces_space_pkey;")
        cursor.execute("ALTER TABLE spaces_session RENAME CONSTRAINT circles_circleevent_pkey TO spaces_session_pkey;")
        cursor.execute(
            "ALTER TABLE spaces_sessionfeedback RENAME CONSTRAINT circles_sessionfeedback_pkey TO spaces_sessionfeedback_pkey;"
        )
        cursor.execute(
            "ALTER TABLE spaces_space_categories RENAME CONSTRAINT circles_circle_categories_pkey TO spaces_space_categories_pkey;"
        )
        cursor.execute(
            "ALTER TABLE spaces_space_subscribed RENAME CONSTRAINT circles_circle_subscribed_pkey TO spaces_space_subscribed_pkey;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session_attendees RENAME CONSTRAINT circles_circleevent_attendees_pkey TO spaces_session_attendees_pkey;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session_joined RENAME CONSTRAINT circles_circleevent_joined_pkey TO spaces_session_joined_pkey;"
        )

        # =====================================================
        # PHASE 8: Rename unique constraints
        # =====================================================
        cursor.execute(
            "ALTER TABLE spaces_spacecategory RENAME CONSTRAINT circles_circlecategory_slug_key TO spaces_spacecategory_slug_key;"
        )
        cursor.execute("ALTER TABLE spaces_space RENAME CONSTRAINT circles_circle_slug_key TO spaces_space_slug_key;")
        cursor.execute(
            "ALTER TABLE spaces_session RENAME CONSTRAINT circles_circleevent_slug_key TO spaces_session_slug_key;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session RENAME CONSTRAINT circles_circleevent_circle_id_start_open_title_345e6ff2_uniq TO spaces_session_space_id_start_open_title_uniq;"
        )
        cursor.execute(
            "ALTER TABLE spaces_sessionfeedback RENAME CONSTRAINT unique_user_feedback_for_event TO unique_user_feedback_for_session;"
        )
        cursor.execute(
            "ALTER TABLE spaces_space_categories RENAME CONSTRAINT circles_circle_categorie_circle_id_circlecategory_931ab1f2_uniq TO spaces_space_categories_space_id_spacecategory_id_uniq;"
        )
        cursor.execute(
            "ALTER TABLE spaces_space_subscribed RENAME CONSTRAINT circles_circle_subscribed_circle_id_user_id_32dcc4a4_uniq TO spaces_space_subscribed_space_id_user_id_uniq;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session_attendees RENAME CONSTRAINT circles_circleevent_atte_circleevent_id_user_id_6eee231f_uniq TO spaces_session_attendees_session_id_user_id_uniq;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session_joined RENAME CONSTRAINT circles_circleevent_joined_circleevent_id_user_id_f11f0553_uniq TO spaces_session_joined_session_id_user_id_uniq;"
        )

        # =====================================================
        # PHASE 9: Rename indexes
        # =====================================================
        cursor.execute("ALTER INDEX circles_circle_author_id_3be3d6f7 RENAME TO spaces_space_author_id;")
        cursor.execute("ALTER INDEX circles_circle_slug_82f7c047_like RENAME TO spaces_space_slug_like;")
        cursor.execute("ALTER INDEX circles_circleevent_circle_id_816ee437 RENAME TO spaces_session_space_id;")
        cursor.execute("ALTER INDEX circles_circleevent_slug_8bcc62e3_like RENAME TO spaces_session_slug_like;")
        cursor.execute("ALTER INDEX circles_circlecategory_slug_ed0f0770_like RENAME TO spaces_spacecategory_slug_like;")
        cursor.execute("ALTER INDEX circles_sessionfeedback_event_id_b0305c8d RENAME TO spaces_sessionfeedback_session_id;")
        cursor.execute("ALTER INDEX circles_sessionfeedback_user_id_88d17eec RENAME TO spaces_sessionfeedback_user_id;")
        cursor.execute(
            "ALTER INDEX circles_circle_categories_circle_id_8ef9be67 RENAME TO spaces_space_categories_space_id;"
        )
        cursor.execute(
            "ALTER INDEX circles_circle_categories_circlecategory_id_ab707200 RENAME TO spaces_space_categories_spacecategory_id;"
        )
        cursor.execute(
            "ALTER INDEX circles_circle_subscribed_circle_id_3da57f69 RENAME TO spaces_space_subscribed_space_id;"
        )
        cursor.execute(
            "ALTER INDEX circles_circle_subscribed_user_id_99082b2c RENAME TO spaces_space_subscribed_user_id;"
        )
        cursor.execute(
            "ALTER INDEX circles_circleevent_attendees_circleevent_id_324eacfb RENAME TO spaces_session_attendees_session_id;"
        )
        cursor.execute(
            "ALTER INDEX circles_circleevent_attendees_user_id_c0299166 RENAME TO spaces_session_attendees_user_id;"
        )
        cursor.execute(
            "ALTER INDEX circles_circleevent_joined_circleevent_id_a7966a11 RENAME TO spaces_session_joined_session_id;"
        )
        cursor.execute(
            "ALTER INDEX circles_circleevent_joined_user_id_38fe1c26 RENAME TO spaces_session_joined_user_id;"
        )

        # =====================================================
        # PHASE 10: Recreate FK constraints with new names
        # =====================================================
        cursor.execute(
            "ALTER TABLE spaces_space ADD CONSTRAINT spaces_space_author_id_fk FOREIGN KEY (author_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session ADD CONSTRAINT spaces_session_space_id_fk FOREIGN KEY (space_id) REFERENCES spaces_space(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_sessionfeedback ADD CONSTRAINT spaces_sessionfeedback_session_id_fk FOREIGN KEY (session_id) REFERENCES spaces_session(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_sessionfeedback ADD CONSTRAINT spaces_sessionfeedback_user_id_fk FOREIGN KEY (user_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_space_categories ADD CONSTRAINT spaces_space_categories_space_id_fk FOREIGN KEY (space_id) REFERENCES spaces_space(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_space_categories ADD CONSTRAINT spaces_space_categories_spacecategory_id_fk FOREIGN KEY (spacecategory_id) REFERENCES spaces_spacecategory(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_space_subscribed ADD CONSTRAINT spaces_space_subscribed_space_id_fk FOREIGN KEY (space_id) REFERENCES spaces_space(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_space_subscribed ADD CONSTRAINT spaces_space_subscribed_user_id_fk FOREIGN KEY (user_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session_attendees ADD CONSTRAINT spaces_session_attendees_session_id_fk FOREIGN KEY (session_id) REFERENCES spaces_session(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session_attendees ADD CONSTRAINT spaces_session_attendees_user_id_fk FOREIGN KEY (user_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session_joined ADD CONSTRAINT spaces_session_joined_session_id_fk FOREIGN KEY (session_id) REFERENCES spaces_session(id) DEFERRABLE INITIALLY DEFERRED;"
        )
        cursor.execute(
            "ALTER TABLE spaces_session_joined ADD CONSTRAINT spaces_session_joined_user_id_fk FOREIGN KEY (user_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("spaces", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(rename_circles_to_spaces, migrations.RunPython.noop),
    ]
