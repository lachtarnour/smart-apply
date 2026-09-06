"""Capture every desktop page against an isolated copy of a database.

Run with .venv/bin/python tools/desktop_visual_check.py --database /path/to/db.
No source availability probes, document generation, or production writes run.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--widths", default="1320,1480,1800")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    output = (args.output or Path(tempfile.mkdtemp(prefix="elan-visual-"))).resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtime = Path(tempfile.mkdtemp(prefix="elan-ui-runtime-"))
    if args.database:
        source = sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)
        with sqlite3.connect(runtime / "visual.db") as target:
            source.backup(target)
        source.close()
    os.environ.update(
        ELAN_HOME=str(runtime),
        ELAN_ENV_FILE=str(runtime / ".env"),
        DATABASE_URL="sqlite:///" + str(runtime / "visual.db"),
        PROFILE_DIR=str(repo / "smartapply/profile/mock_profile"),
        OUTPUT_DIR=str(runtime / "documents"),
        CACHE_DIR=str(runtime / "cache"),
        QT_QPA_PLATFORM="offscreen",
        QT_QUICK_CONTROLS_STYLE="Basic",
        QT_QUICK_BACKEND="software",
        QSG_RHI_BACKEND="software",
    )
    from PySide6.QtCore import (
        QCoreApplication,
        QEvent,
        QObject,
        QPointF,
        Qt,
        qInstallMessageHandler,
    )
    from PySide6.QtGui import QFont, QGuiApplication, QKeyEvent
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from smartapply.desktop import app as desktop
    from smartapply.desktop.bridge import DesktopBridge
    from smartapply.desktop.services import DesktopService

    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    application = QGuiApplication([])
    application.setFont(QFont(".AppleSystemUIFont", 13))
    service = DesktopService()
    local_diagnostics = service.diagnostics
    service.diagnostics = lambda **kwargs: local_diagnostics(check_sources=False)
    bridge = DesktopBridge(service)
    desktop.DesktopBridge = lambda: bridge
    engine, _ = desktop.create_engine(application)
    window = engine.rootObjects()[0]
    checks = []

    def check(condition, name):
        checks.append({"name": name, "passed": bool(condition)})

    def item(name):
        found = window.findChild(QObject, name)
        # ListView delegates belong to the visual tree, not always the QObject tree.
        if found is None:
            pending = [window.contentItem()]
            while pending:
                candidate = pending.pop()
                if candidate.objectName() == name:
                    found = candidate
                    break
                pending.extend(candidate.childItems())
        if found is None:
            raise RuntimeError(f"Missing UI element: {name}")
        return found

    def click(name):
        control = item(name)
        if not isinstance(control, QQuickItem):
            raise RuntimeError(f"Not a visual item: {name}")
        center = control.mapToScene(QPointF(control.width() / 2, control.height() / 2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center.toPoint())
        QTest.qWait(220)

    def type_text(value):
        for character in value:
            application.sendEvent(window, QKeyEvent(QEvent.KeyPress, 0, Qt.NoModifier, character))
            application.sendEvent(window, QKeyEvent(QEvent.KeyRelease, 0, Qt.NoModifier, character))

    def settle():
        QTest.qWait(400)
        for _ in range(1200):
            application.processEvents()
            time.sleep(0.01)  # Release the GIL for the bridge's Python workers.
            if not bridge._workers and not bridge._read_workers:
                break
        QTest.qWait(450)

    def capture(name):
        check(window.title() == "", f"{name}: native title bar has no app name")
        pages = window.findChild(QObject, "pages")
        check(pages is not None and pages.property("opacity") >= 0.99, f"{name}: page visible")
        pixmap = window.grabWindow()
        check(not pixmap.isNull(), f"{name}: capture rendered")
        pixmap.save(str(output / (name + ".png")))
        if name.startswith("jobs-") and bridge.jobs and bridge.currentJob.get("id"):
            check(not bridge.jobDetailLoading, f"{name}: offer detail has finished loading")
            dossier_id = (bridge.currentJob.get("application") or {}).get("id")
            dossier_number = item("offerDossierNumber")
            check(
                dossier_number.property("visible") == bool(dossier_id)
                and dossier_number.property("text") == (f"#{dossier_id}" if dossier_id else ""),
                f"{name}: displayed number identifies the dossier, not the offer",
            )
            job_id = str(bridge.currentJob["id"])
            columns = [
                item("offer" + column + "-" + job_id)
                for column in (
                    "Selection",
                    "Company",
                    "Title",
                    "Experience",
                    "Location",
                    "Ia",
                    "Match",
                )
            ]
            check(
                all(
                    left.mapToScene(QPointF(left.width(), 0)).x() + 4
                    <= right.mapToScene(QPointF(0, 0)).x()
                    for left, right in zip(columns[:-1], columns[1:], strict=True)
                ),
                f"{name}: table columns do not overlap",
            )
            check(columns[2].width() >= 140, f"{name}: job title has usable width")
            check(columns[2].property("lineCount") <= 2, f"{name}: title stays within two lines")
            for column, header in ((1, "Company"), (2, "Title"), (6, "Match")):
                check(
                    abs(
                        columns[column].mapToScene(QPointF(0, 0)).x()
                        - item("offer" + header + "Header").mapToScene(QPointF(0, 0)).x()
                    )
                    < 1,
                    f"{name}: {header} header aligned with cells",
                )
            check(
                columns[-1].mapToScene(QPointF(columns[-1].width(), 0)).x() + 4
                <= item("offerTableScrollBar").mapToScene(QPointF(0, 0)).x(),
                f"{name}: scrollbar does not cover scores",
            )
            if (
                bridge.currentJob.get("llm_score") is not None
                and bridge.currentJob.get("score") is not None
            ):
                check(
                    columns[-1].property("color") == columns[-2].property("color")
                    and columns[-1].property("font") == columns[-2].property("font"),
                    f"{name}: IA and Match use the same neutral style",
                )

    routes = [
        "dashboard",
        "search",
        "duplicates",
        "jobs?status=ready_for_form_submission",
        "manual",
        "profile",
        "settings",
    ]
    for width in map(int, args.widths.split(",")):
        window.setWidth(width)
        window.setHeight(820 if width == 1320 else 920 if width == 1480 else 1000)
        for route in routes:
            window.navigate(route)
            settle()
            capture(f"{route.split('?')[0]}-{width}")
    # Keep the final page at the standard size for state captures.
    window.setWidth(1480)
    window.setHeight(920)
    window.navigate("jobs?status=ready_for_form_submission")
    settle()
    page = window.findChild(QObject, "jobsPage")
    search = window.findChild(QObject, "expandableSearch")
    if search:
        search.setProperty("expanded", True)
    if page and bridge.jobs:
        page.setProperty("selectedJobs", {str(row["id"]): True for row in bridge.jobs[:3]})
    QTest.qWait(300)
    capture("jobs-selection-search")
    window.navigate("jobs?status=archived")
    settle()
    capture("jobs-archived")
    page_position = item("jobsPage").mapToScene(QPointF(0, 0))
    bridge.toastRequested.emit("Modification enregistrée", "Votre espace est à jour.", "success")
    QTest.qWait(300)
    check(
        page_position == item("jobsPage").mapToScene(QPointF(0, 0)),
        "Notification does not shift page",
    )
    capture("notification")
    click("toastDismiss")
    check(not item("toast").property("visible"), "Notification can be dismissed")
    # Real user interactions, without clicking any business mutation.
    window.navigate("manual")
    settle()
    check(not item("manualCreate").property("enabled"), "Empty form cannot be submitted")
    check(
        not item("manualDescriptionValidation").property("visible"),
        "No permanent form instructions",
    )
    click("manualTitle")
    type_text("Machine Learning Engineer")
    QTest.keyClick(window, Qt.Key_Tab)
    type_text("Entreprise de demonstration")
    check(item("manualCompany").property("text") == "Entreprise de demonstration", "Form tab order")
    item("manualDescription").setProperty("text", "Description courte")
    check(not item("manualCreate").property("enabled"), "Short description cannot be submitted")
    check(
        item("manualDescriptionValidation").property("visible"),
        "Short description shows validation",
    )
    item("manualDescription").setProperty(
        "text",
        "Construire des services Python et des modeles de machine learning fiables pour nos clients.",
    )
    QTest.qWait(150)
    check(item("manualCreate").property("enabled"), "Complete form can be submitted")
    check(
        not item("manualDescriptionValidation").property("visible"),
        "Valid description hides validation",
    )
    check(
        abs(item("manualTitle").width() - item("manualCompany").width()) < 2, "Form columns equal"
    )
    capture("manual-filled")

    window.navigate("jobs?status=ready_for_form_submission")
    settle()
    page = item("jobsPage")
    item("expandableSearch").close(True)
    QTest.qWait(250)
    click("offerSearchToggle")
    check(item("expandableSearch").property("expanded"), "Search button expands")
    type_text("Citalid")
    settle()
    check(
        bool(bridge.jobs) and all("citalid" in str(row).lower() for row in bridge.jobs),
        "Offer search filters results",
    )
    QTest.keyClick(window, Qt.Key_Escape)
    settle()
    check(
        not item("expandableSearch").property("expanded") and len(bridge.jobs) > 1,
        "Escape clears and collapses search",
    )
    for header, key in (("Company", "company"), ("Title", "title")):
        click("offer" + header + "Header")
        settle()
        values = [row[key] for row in bridge.jobs if row.get(key) is not None]
        check(
            page.property("sortKey") == key and values == sorted(values),
            f"{header} header sorts offers ascending",
        )
        click("offer" + header + "Header")
        settle()
        values = [row[key] for row in bridge.jobs if row.get(key) is not None]
        check(values == sorted(values, reverse=True), f"{header} header reverses sort order")
    click("offerMatchHeader")
    settle()
    scores = [row["score"] for row in bridge.jobs if row.get("score") is not None]
    check(
        page.property("sortKey") == "score" and scores == sorted(scores, reverse=True),
        "Match header restores descending score order",
    )
    page.clearSelection()
    selection_name = "offerSelection-" + str(bridge.currentJob["id"])
    click(selection_name)
    check(
        item(selection_name).property("checked") and page.property("selectedCount") == 1,
        "Row checkbox selects offer",
    )
    click(selection_name)
    check(
        not item(selection_name).property("checked") and page.property("selectedCount") == 0,
        "Row checkbox clears selection",
    )
    settle()
    shortlist_snapshot = bridge._shortlist.copy()
    bridge._shortlist = dict(shortlist_snapshot, ready_to_generate=12)
    bridge.shortlistChanged.emit()
    for toolbar_width in (1320, 1559, 1560, 1800):
        window.setWidth(toolbar_width)
        click("offerSearchToggle")
        QTest.qWait(300)
        check(
            item("offerSearchField").width() >= 100,
            f"Search with generation button at {toolbar_width}px",
        )
        shortlist_right = (
            item("offerShortlistControls")
            .mapToItem(item("offerToolbar"), QPointF(item("offerShortlistControls").width(), 0))
            .x()
        )
        check(
            shortlist_right <= item("offerToolbar").width() + 1,
            f"Toolbar stays above table at {toolbar_width}px",
        )
        capture(f"jobs-toolbar-{toolbar_width}")
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.qWait(200)
    bridge._shortlist = shortlist_snapshot
    bridge.shortlistChanged.emit()
    window.setWidth(1480)
    QTest.qWait(250)
    before_zoom = page.property("detailTextZoom")
    click("detailZoomButton")
    check(item("detailZoomPopup").property("opened"), "Text-size control opens")
    click("detailZoomIn")
    check(page.property("detailTextZoom") > before_zoom, "Text enlarges immediately")
    click("detailZoomReset")
    check(abs(page.property("detailTextZoom") - 1.15) < 0.001, "Text size resets to default")
    capture("jobs-text-controls")
    QTest.keyClick(window, Qt.Key_Escape)
    check(not item("detailZoomPopup").property("opened"), "Text-size control closes with Escape")
    page.setProperty("detailTextZoom", 1.55)
    QTest.qWait(220)
    capture("jobs-text-large")
    page.setProperty("detailTextZoom", 1.15)
    item("commandPalette").open()
    QTest.qWait(250)
    type_text("Profil")
    capture("navigation-keyboard")
    QTest.keyClick(window, Qt.Key_Return)
    settle()
    check(window.property("currentRoute") == "profile", "Keyboard page navigation")

    # Stress fixtures only replace in-memory presentation data, never database rows.
    profile_snapshot = bridge._profile.copy()
    bridge._profile = dict(
        profile_snapshot,
        name="Camille Martin — Ingénieure intelligence artificielle",
        summary="Ingénieure en intelligence artificielle, spécialisée dans les systèmes de données et le déploiement de modèles fiables. "
        * 4,
        skill_categories=[
            {
                "name": "Domaine technique " + str(i),
                "skills": ["Compétence spécialisée " + str(j) for j in range(7)],
            }
            for i in range(7)
        ],
    )
    bridge.profileChanged.emit()
    QTest.qWait(250)
    capture("profile-long-content")
    bridge._profile = profile_snapshot
    bridge.profileChanged.emit()
    window.navigate("search")
    settle()
    diagnostics_snapshot = bridge._diagnostics.copy()
    bridge._diagnostics = dict(
        diagnostics_snapshot,
        source_ready={
            "serpapi": True,
            "francetravail": True,
            "linkedin": True,
            "welcometothejungle": True,
        },
    )
    bridge.diagnosticsChanged.emit()
    QTest.qWait(220)
    capture("search-sources-connected-fixture")
    bridge._diagnostics = diagnostics_snapshot
    bridge.diagnosticsChanged.emit()
    window.navigate("duplicates")
    settle()
    bridge._jobs = [
        {
            "id": 9001,
            "company": "Entreprise de démonstration",
            "title": "Ingénieur Machine Learning & Data Platform",
            "source": "linkedin",
            "duplicate_confidence": 0.91,
        }
    ]
    bridge._current_job = dict(
        bridge._jobs[0],
        location="Paris, Île-de-France, France",
        contract="CDI",
        remote="Hybride",
        description="Concevoir des pipelines de données, entraîner et déployer des modèles de machine learning. "
        * 8,
        duplicate_candidate={
            "id": 9002,
            "title": "Machine Learning Engineer — Data Platform",
            "company": "Entreprise de démonstration",
            "location": "75 — Paris",
            "contract": "CDI",
            "source": "welcometothejungle",
            "application_id": 99,
            "application_status": "archived",
            "application_status_label": "Archivée",
            "description": "Développer une plateforme de données et industrialiser des modèles de machine learning. "
            * 8,
        },
    )
    bridge.jobsChanged.emit()
    bridge.currentJobChanged.emit()
    window.setWidth(1320)
    window.setHeight(820)
    QTest.qWait(300)
    capture("duplicates-comparison-fixture")
    errors = [
        msg
        for msg in messages
        if any(
            token in msg
            for token in (
                "Error",
                "Unable to",
                "Binding loop",
                "Cannot assign",
                "is not defined",
                "Cannot anchor",
                "does not support customization",
                "Detected anchors",
            )
        )
    ]
    failed = [entry["name"] for entry in checks if not entry["passed"]]
    (output / "diagnostics.json").write_text(
        json.dumps(
            {"errors": errors, "messages": messages, "checks": checks}, ensure_ascii=False, indent=2
        )
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "captures": len(list(output.glob("*.png"))),
                "errors": errors,
                "failed_checks": failed,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    bridge._thread_pool.waitForDone()
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    application.processEvents()
    qInstallMessageHandler(None)
    application.quit()
    return 1 if errors or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
