import almonium_book_processor.catalog.models
import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Chapter',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('sequence', models.PositiveIntegerField()),
                ('title', models.CharField(blank=True, max_length=500)),
            ],
            options={
                'ordering': ['edition', 'sequence'],
            },
        ),
        migrations.CreateModel(
            name='ModelConfiguration',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120, unique=True)),
                ('provider', models.CharField(max_length=50)),
                ('model', models.CharField(max_length=120)),
                ('purpose', models.CharField(max_length=50)),
                ('parameters', models.JSONField(blank=True, default=dict)),
                ('enabled', models.BooleanField(default=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Work',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('slug', models.SlugField(max_length=160, unique=True)),
                ('title', models.CharField(max_length=500)),
                ('author', models.CharField(max_length=300)),
                ('original_language', models.CharField(max_length=35)),
                ('first_published_year', models.PositiveSmallIntegerField(blank=True, null=True)),
            ],
            options={
                'ordering': ['author', 'title'],
            },
        ),
        migrations.CreateModel(
            name='Edition',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('slug', models.SlugField(max_length=180, unique=True)),
                ('title', models.CharField(max_length=500)),
                ('author', models.CharField(max_length=300)),
                ('language', models.CharField(max_length=35)),
                ('edition_type', models.CharField(choices=[('original', 'Original'), ('human_translation', 'Human translation'), ('machine_translation', 'Machine translation'), ('adaptation', 'Level adaptation'), ('abridgement', 'Abridgement')], default='original', max_length=32)),
                ('translator', models.CharField(blank=True, max_length=300)),
                ('cefr_target', models.CharField(blank=True, max_length=2)),
                ('schema_version', models.PositiveSmallIntegerField(default=2)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('queued', 'Queued'), ('processing', 'Processing'), ('review', 'Needs review'), ('ready', 'Ready'), ('published', 'Published'), ('failed', 'Failed')], default='draft', max_length=20)),
                ('word_count', models.PositiveIntegerField(default=0)),
                ('confidence', models.FloatField(blank=True, null=True)),
                ('source_file', models.FileField(blank=True, upload_to=almonium_book_processor.catalog.models.source_upload_path, validators=[django.core.validators.FileExtensionValidator(['epub'])])),
                ('source_sha256', models.CharField(blank=True, max_length=64)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('source_edition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='derived_editions', to='catalog.edition')),
                ('work', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='editions', to='catalog.work')),
            ],
            options={
                'ordering': ['work__author', 'work__title', 'language'],
            },
        ),
        migrations.CreateModel(
            name='ContentBlock',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('block_id', models.CharField(max_length=80)),
                ('sequence', models.PositiveIntegerField()),
                ('block_type', models.CharField(choices=[('paragraph', 'Paragraph'), ('heading', 'Heading'), ('verse_line', 'Verse line'), ('verse_stanza', 'Verse stanza'), ('blockquote', 'Block quote'), ('letter', 'Letter'), ('epigraph', 'Epigraph'), ('dialogue', 'Dialogue'), ('footnote', 'Footnote'), ('image', 'Image'), ('separator', 'Separator')], max_length=20)),
                ('text', models.TextField(blank=True)),
                ('sentences', models.JSONField(blank=True, default=list)),
                ('align_group', models.UUIDField(blank=True, null=True)),
                ('source_ref', models.CharField(blank=True, max_length=1000)),
                ('attributes', models.JSONField(blank=True, default=dict)),
                ('chapter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blocks', to='catalog.chapter')),
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blocks', to='catalog.edition')),
            ],
            options={
                'ordering': ['edition', 'chapter__sequence', 'sequence'],
            },
        ),
        migrations.AddField(
            model_name='chapter',
            name='edition',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chapters', to='catalog.edition'),
        ),
        migrations.CreateModel(
            name='PipelineRun',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stage', models.CharField(choices=[('ingest', 'EPUB ingestion'), ('sentences', 'Sentence splitting'), ('align', 'Alignment'), ('translate', 'Translation'), ('adapt', 'Level adaptation'), ('publish', 'Publication')], max_length=20)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('succeeded', 'Succeeded'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='queued', max_length=20)),
                ('idempotency_key', models.CharField(max_length=255, unique=True)),
                ('processor_version', models.CharField(max_length=40)),
                ('input_hash', models.CharField(max_length=64)),
                ('progress', models.PositiveSmallIntegerField(default=0)),
                ('confidence', models.FloatField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('summary', models.JSONField(blank=True, default=dict)),
                ('error', models.TextField(blank=True)),
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pipeline_runs', to='catalog.edition')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PromptTemplate',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('version', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('purpose', models.CharField(max_length=50)),
                ('system_prompt', models.TextField()),
                ('user_template', models.TextField()),
                ('output_schema', models.JSONField(default=dict)),
                ('active', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ['name', '-version'],
                'constraints': [models.UniqueConstraint(fields=('name', 'version'), name='catalog_prompt_name_version_unique')],
            },
        ),
        migrations.CreateModel(
            name='AIRun',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('submitted', 'Submitted'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], default='queued', max_length=20)),
                ('provider_request_id', models.CharField(blank=True, max_length=255)),
                ('input_tokens', models.PositiveIntegerField(default=0)),
                ('output_tokens', models.PositiveIntegerField(default=0)),
                ('estimated_cost_usd', models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ('request_payload', models.JSONField(default=dict)),
                ('response_payload', models.JSONField(default=dict)),
                ('error', models.TextField(blank=True)),
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_runs', to='catalog.edition')),
                ('model_configuration', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='catalog.modelconfiguration')),
                ('pipeline_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ai_runs', to='catalog.pipelinerun')),
                ('prompt_template', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='catalog.prompttemplate')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='QAWarning',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('code', models.CharField(max_length=100)),
                ('severity', models.CharField(choices=[('info', 'Info'), ('warning', 'Warning'), ('error', 'Error')], default='warning', max_length=10)),
                ('message', models.TextField()),
                ('source_ref', models.CharField(blank=True, max_length=1000)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('block', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='warnings', to='catalog.contentblock')),
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='warnings', to='catalog.edition')),
                ('pipeline_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='warnings', to='catalog.pipelinerun')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_book_warnings', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['resolved_at', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='UserErrorReport',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reporter_user_id', models.UUIDField(blank=True, null=True)),
                ('message', models.TextField()),
                ('status', models.CharField(choices=[('open', 'Open'), ('resolved', 'Resolved'), ('dismissed', 'Dismissed')], default='open', max_length=20)),
                ('block', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='error_reports', to='catalog.contentblock')),
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='error_reports', to='catalog.edition')),
            ],
            options={
                'ordering': ['status', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='contentblock',
            index=models.Index(fields=['edition', 'align_group'], name='catalog_con_edition_5d721a_idx'),
        ),
        migrations.AddConstraint(
            model_name='contentblock',
            constraint=models.UniqueConstraint(fields=('edition', 'block_id'), name='catalog_block_edition_block_id_unique'),
        ),
        migrations.AddConstraint(
            model_name='contentblock',
            constraint=models.UniqueConstraint(fields=('chapter', 'sequence'), name='catalog_block_chapter_sequence_unique'),
        ),
        migrations.AddConstraint(
            model_name='chapter',
            constraint=models.UniqueConstraint(fields=('edition', 'sequence'), name='catalog_chapter_edition_sequence_unique'),
        ),
        migrations.AddIndex(
            model_name='pipelinerun',
            index=models.Index(fields=['status', 'created_at'], name='catalog_pip_status_a5d006_idx'),
        ),
        migrations.AddIndex(
            model_name='qawarning',
            index=models.Index(fields=['edition', 'resolved_at'], name='catalog_qaw_edition_e6d840_idx'),
        ),
        migrations.AddIndex(
            model_name='edition',
            index=models.Index(fields=['status', 'updated_at'], name='catalog_edi_status_2f15ad_idx'),
        ),
        migrations.AddIndex(
            model_name='edition',
            index=models.Index(fields=['work', 'language'], name='catalog_edi_work_id_7128eb_idx'),
        ),
    ]
