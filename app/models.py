from __future__ import annotations

from datetime import datetime

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    Model,
    TextField,
)

from app.database import database


def now_local() -> datetime:
    return datetime.now().replace(microsecond=0)


class BaseModel(Model):
    class Meta:
        database = database


class Account(BaseModel):
    phone = CharField(max_length=32, unique=True)
    cookies = TextField()
    note = CharField(max_length=255, default="")
    is_disabled = BooleanField(default=False)
    created_at = DateTimeField(default=now_local)
    updated_at = DateTimeField(default=now_local)


class AppSetting(BaseModel):
    key = CharField(max_length=64, unique=True)
    value = TextField(default="")
    created_at = DateTimeField(default=now_local)
    updated_at = DateTimeField(default=now_local)


class RewritePrompt(BaseModel):
    content = TextField()
    sort_order = IntegerField(default=0)
    created_at = DateTimeField(default=now_local)
    updated_at = DateTimeField(default=now_local)


class TaskRecord(BaseModel):
    account_id = IntegerField(index=True)
    account_phone = CharField(max_length=32, default="")
    account_note = CharField(max_length=255, default="")
    account_cookies = TextField(default="")
    project_pid = CharField(max_length=64, default="", index=True)
    article_id = IntegerField(null=True, index=True)
    rewritten_content = TextField(default="")
    title = TextField(default="")
    rewrite_prompt_id = IntegerField(null=True)
    rewrite_prompt = TextField(default="")
    progress = IntegerField(default=0)
    status = CharField(max_length=64, default="待处理")
    huasheng_status = CharField(max_length=128, default="")
    video_url = TextField(default="")
    export_task_id = CharField(max_length=128, default="")
    export_version = CharField(max_length=64, default="")
    created_at = DateTimeField(default=now_local)
    updated_at = DateTimeField(default=now_local)


class HuashengGenerationRecord(BaseModel):
    account_id = IntegerField(index=True)
    project_pid = CharField(max_length=64, unique=True)
    generated_at = DateTimeField(default=now_local, index=True)


class BenchmarkAccount(BaseModel):
    url = CharField(max_length=2048, unique=True)
    created_at = DateTimeField(default=now_local)
    updated_at = DateTimeField(default=now_local)
    last_monitored_at = DateTimeField(null=True)


class MonitorRun(BaseModel):
    benchmark_account = ForeignKeyField(
        BenchmarkAccount,
        backref="monitor_runs",
        on_delete="CASCADE",
    )
    source_url = CharField(max_length=2048)
    status = CharField(max_length=32, default="running")
    warning = TextField(null=True)
    article_count = IntegerField(default=0)
    started_at = DateTimeField(default=now_local)
    finished_at = DateTimeField(null=True)


class MonitoredArticle(BaseModel):
    benchmark_account = ForeignKeyField(
        BenchmarkAccount,
        backref="articles",
        on_delete="CASCADE",
    )
    monitor_run = ForeignKeyField(
        MonitorRun,
        backref="articles",
        on_delete="SET NULL",
        null=True,
    )
    dedupe_key = CharField(max_length=255, unique=True)
    item_id = CharField(max_length=255, null=True)
    group_id = CharField(max_length=255, null=True)
    cell_type = CharField(max_length=64, null=True)
    title = TextField(null=True)
    content = TextField(null=True)
    publish_time = DateTimeField(null=True)
    source = CharField(max_length=255, null=True)
    media_name = CharField(max_length=255, null=True)
    display_url = TextField(null=True)
    play_count = IntegerField(null=True)
    digg_count = IntegerField(null=True)
    comment_count = IntegerField(null=True)
    forward_count = IntegerField(null=True)
    bury_count = IntegerField(null=True)
    raw_json = TextField(null=True)
    isdelete = IntegerField(default=0)
    created_at = DateTimeField(default=now_local)
    updated_at = DateTimeField(default=now_local)
