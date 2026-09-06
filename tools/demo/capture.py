"""Capture the native app with its real workflow and isolated demo providers."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import replace
from pathlib import Path

from fixtures import REPO, configure, install_providers, seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=REPO / "data/demo")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    configure(runtime, reset=args.reset)
    sys.path.insert(0, str(REPO))
    os.environ.update(QT_QUICK_CONTROLS_STYLE="Basic")
    if not args.interactive:
        os.environ.update(
            QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QSG_RHI_BACKEND="software"
        )
    install_providers(delay=0.55)
    from PySide6.QtCore import QObject, QPointF, Qt
    from PySide6.QtGui import QFont, QGuiApplication
    from PySide6.QtTest import QTest
    from sqlalchemy import select

    from smartapply.database import session_scope
    from smartapply.database.models import Application, Job
    from smartapply.desktop import app as desktop
    from smartapply.desktop.bridge import DesktopBridge
    from smartapply.desktop.services import DesktopService
    from smartapply.desktop.source_health import SourceHealth

    if args.reset or not (runtime / "demo.db").exists():
        seed()
    app = QGuiApplication([])
    app.setFont(QFont(".AppleSystemUIFont", 13))
    service = DesktopService()
    original_diagnostics = service.diagnostics

    def diagnostics(**kwargs):
        result = original_diagnostics(check_sources=False)
        health = dict(result.source_health)
        health["serpapi"] = SourceHealth(True, True, "ready", "Source de démonstration locale")
        return replace(
            result, source_health=health, source_ready={k: v.ready for k, v in health.items()}
        )

    service.diagnostics = diagnostics
    bridge = DesktopBridge(service)
    desktop.DesktopBridge = lambda: bridge
    engine, _ = desktop.create_engine(app)
    window = engine.rootObjects()[0]
    window.setWidth(1600)
    window.setHeight(900)
    if args.interactive:
        return app.exec()
    shots = runtime / "captures"
    shots.mkdir(exist_ok=True)
    manifest = []
    events = []
    bridge.toastRequested.connect(
        lambda title, message, kind: events.append(dict(title=title, message=message, kind=kind))
    )

    def items():
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            yield item
            pending.extend(reversed(item.childItems()))

    def find(name=None, text=None, placeholder=None):
        for item in items():
            if name and item.objectName() == name:
                return item
            if not item.isVisible():
                continue
            if text and item.property("text") == text and hasattr(item, "clicked"):
                return item
            if placeholder and item.property("placeholderText") == placeholder:
                return item
        raise RuntimeError(f"Control not found: {name or text or placeholder}")

    def rect(item):
        pt = item.mapToScene(QPointF(0, 0))
        return [round(pt.x()), round(pt.y()), round(item.width()), round(item.height())]

    def settle():
        QTest.qWait(650)
        deadline = time.monotonic() + 90
        while bridge._workers or bridge._read_workers:
            QTest.qWait(30)
            if time.monotonic() > deadline:
                raise RuntimeError("Desktop worker timeout")
        QTest.qWait(500)

    def save(name, **meta):
        if name != "03-fetch":
            try:
                dismiss = find(name="toastDismiss")
                if dismiss.isVisible():
                    click(dismiss)
                    QTest.qWait(180)
            except RuntimeError:
                pass
        target = shots / f"{name}.png"
        frame = window.grabWindow()
        assert not frame.isNull() and frame.save(str(target))
        manifest.append(dict(name=name, image=str(target), **meta))
        print(f"CAPTURE {name}", flush=True)

    def click(item):
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())

    def checkpoint(name):
        with (
            sqlite3.connect(runtime / "demo.db") as src,
            sqlite3.connect(runtime / f"{name}.db") as dst,
        ):
            src.backup(dst)

    settle()
    checkpoint("start")
    save("01-home", focus=[250, 100, 1300, 152])
    window.navigate("search")
    settle()
    find(name="searchQuery").setProperty("text", "Data Scientist OR Machine Learning Engineer")
    find(placeholder="Ville, région ou pays").setProperty("text", "Paris, France")
    for item in items():
        if item.isVisible() and item.property("from") == 1 and item.property("to") == 100:
            item.setProperty("value", 3)
    QTest.qWait(250)
    search = find(text="Rechercher")
    save("02-search", focus=[260, 104, 1270, 280], cursor=rect(search))
    click(search)
    QTest.qWait(450)
    save("03-fetch", focus=[260, 392, 1270, 225])
    settle()
    assert bridge.activity["fetched"] == 3, bridge.activity
    checkpoint("after-fetch")
    window.navigate("duplicates")
    settle()
    assert len(bridge.jobs) == 2, bridge.jobs
    save("04-duplicates", focus=[250, 103, 380, 320])
    save("05-compare", focus=[650, 167, 880, 450], cursor=rect(find(text="Même offre")))
    click(find(text="Même offre"))
    settle()
    assert len(bridge.jobs) == 1, bridge.jobs
    save("06-second-duplicate", focus=[650, 167, 880, 460], cursor=rect(find(text="Même offre")))
    click(find(text="Même offre"))
    settle()
    assert len(bridge.jobs) == 0
    save("07-resolved", focus=[500, 360, 680, 170])
    checkpoint("after-duplicates")
    window.navigate("jobs?status=scraped")
    settle()
    bridge.selectJob(1)
    settle()
    assert len(bridge.jobs) == 3, bridge.jobs
    save("08-offers", focus=rect(find(name="offerTable")))
    click(find(text="Analyser"))
    settle()
    window.navigate("jobs?status=analyzed")
    settle()
    bridge.selectJob(1)
    settle()
    save("09-analysis", focus=[960, 112, 598, 540], cursor=rect(find(text="Créer")))
    click(find(text="Créer"))
    QTest.qWait(180)
    save("10-generation", focus=[960, 110, 598, 714])
    settle()
    window.navigate("jobs?status=ready_for_form_submission")
    settle()
    bridge.selectJob(1)
    settle()
    assert bridge.currentJob.get("application", {}).get("cv_pdf_path"), events
    save("11-documents", focus=[960, 640, 598, 232], cursor=rect(find(text="CV")))
    # Exercise the same native document buttons; intercept only OS dispatch so
    # the capture does not open the user's Preview app or change their desktop.
    from PySide6.QtGui import QDesktopServices

    class DocumentSink(QObject):
        from PySide6.QtCore import Slot

        @Slot("QUrl")
        def open(self, url):
            events.append({"opened_document": url.toLocalFile()})

    sink = DocumentSink()
    QDesktopServices.setUrlHandler("file", sink, "open")
    for label in ("CV", "Lettre"):
        click(find(text=label))
        QTest.qWait(100)
    QDesktopServices.unsetUrlHandler("file")
    window.navigate("dashboard")
    settle()
    save("12-final", focus=[250, 100, 1300, 152])
    with session_scope() as session:
        jobs = session.scalars(select(Job).order_by(Job.id)).all()
        application = session.scalar(select(Application).where(Application.job_id == 1))
        audit = dict(
            jobs=[
                dict(
                    id=j.id,
                    company=j.company,
                    status=j.status,
                    canonical_id=j.canonical_job_id,
                    duplicate_status=j.duplicate_review_status,
                )
                for j in jobs
            ],
            application=dict(
                id=application.id,
                status=application.status,
                warnings=application.validation_warnings,
                documents=[dict(type=d.doc_type, path=d.path) for d in application.documents],
            ),
            events=events,
        )
        assert sum(j.canonical_job_id is not None for j in jobs) == 2
        assert application.status == "ready_for_form_submission", audit
        assert not application.validation_warnings, application.validation_warnings
    (runtime / "capture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    (runtime / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)
    # Keep the engine and bridge alive through the last frame.
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
