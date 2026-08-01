import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BlockAlignment',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('group_id', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('confidence', models.FloatField()),
                ('strategy', models.CharField(max_length=80)),
                ('source_block', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='outgoing_alignments', to='catalog.contentblock')),
                ('source_edition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='source_alignments', to='catalog.edition')),
                ('target_block', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incoming_alignments', to='catalog.contentblock')),
                ('target_edition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='target_alignments', to='catalog.edition')),
            ],
            options={
                'ordering': ['target_edition', 'target_block__sequence'],
                'indexes': [models.Index(fields=['source_edition', 'target_edition', 'confidence'], name='catalog_blo_source__c4c007_idx')],
                'constraints': [models.UniqueConstraint(fields=('source_edition', 'target_edition', 'source_block', 'target_block'), name='catalog_alignment_block_pair_unique')],
            },
        ),
    ]
