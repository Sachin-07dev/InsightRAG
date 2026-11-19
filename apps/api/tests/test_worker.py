def test_json_only_worker_and_idempotent_eager_diagnostic(monkeypatch, tmp_path):
    file = tmp_path / "redis_url"
    file.write_text("redis://127.0.0.1:6379/0", encoding="utf-8")
    monkeypatch.setenv("INSIGHTRAG_REDIS_URL_FILE", str(file))
    from insightrag.core.config import Settings
    from insightrag.worker import create_celery

    app = create_celery(Settings(_env_file=None, redis_url_file=file))
    app.conf.update(task_always_eager=True, task_store_eager_result=False)
    assert app.conf.accept_content == ["json"]
    task = app.tasks["insightrag.diagnostics.ping"]
    assert task.delay().get() == {"status": "ok"}
    assert task.delay().get() == {"status": "ok"}
    app.close()
