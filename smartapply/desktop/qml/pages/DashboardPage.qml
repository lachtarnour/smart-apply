import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root
    signal navigateRequested(string route)

    readonly property int jobCount: Number(AppBridge.dashboard.jobs || 0)
    readonly property int pendingCount: Number(AppBridge.dashboard.pending || 0)
    readonly property int readyCount: Number(AppBridge.dashboard.ready || 0)
    readonly property int reviewCount: Number(AppBridge.dashboard.review || 0)
    readonly property int sentCount: Number(AppBridge.dashboard.sent || 0)
    readonly property int applicationCount: readyCount + reviewCount + sentCount

    function focusRoute() {
        if (readyCount > 0 || reviewCount > 0) return "applications"
        if (pendingCount > 0) return "jobs"
        if (jobCount > 0) return "jobs"
        return "search"
    }

    function focusLabel() {
        if (readyCount > 0) return readyCount + " CANDIDATURE" + (readyCount === 1 ? " À RELIRE" : "S À RELIRE")
        if (reviewCount > 0) return reviewCount + " CANDIDATURE" + (reviewCount === 1 ? " À COMPLÉTER" : "S À COMPLÉTER")
        if (pendingCount > 0) return pendingCount + " OFFRE" + (pendingCount === 1 ? " À ANALYSER" : "S À ANALYSER")
        if (sentCount > 0) return sentCount + " CANDIDATURE" + (sentCount === 1 ? " ENVOYÉE" : "S ENVOYÉES")
        if (jobCount > 0) return jobCount + " OFFRE" + (jobCount === 1 ? " ENREGISTRÉE" : "S ENREGISTRÉES")
        return "COMMENCER"
    }

    function focusTitle() {
        if (readyCount > 0) return "Documents à relire"
        if (reviewCount > 0) return "Candidatures à compléter"
        if (pendingCount > 0) return "Offres à analyser"
        if (sentCount > 0) return "Candidatures envoyées"
        if (jobCount > 0) return "Offres à sélectionner"
        return "Commencez votre recherche"
    }

    function focusButton() {
        if (readyCount > 0 || reviewCount > 0) return "Candidatures"
        if (pendingCount > 0 || jobCount > 0) return "Offres"
        return "Rechercher"
    }

    function journeyStep() {
        if (sentCount > 0) return 3
        if (readyCount > 0 || reviewCount > 0) return 2
        if (jobCount > 0) return 1
        return 0
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight + 30
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: AppScrollBar { }

        ColumnLayout {
            id: content
            width: parent.width - 12
            spacing: 17

            PageHeader {
                Layout.fillWidth: true
                title: "Aujourd’hui"
                AppButton {
                    text: "Nouvelle recherche"
                    iconSource: Theme.icon("plus")
                    kind: "primary"
                    onClicked: root.navigateRequested("search")
                }
            }

            Rectangle {
                id: hero
                Layout.fillWidth: true
                Layout.preferredHeight: 264
                radius: 28
                clip: true
                border.color: "#4B435F"
                border.width: 1
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "#15131C" }
                    GradientStop { position: 0.52; color: "#1D1928" }
                    GradientStop { position: 1.0; color: "#30264C" }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: 28
                    anchors.rightMargin: 28
                    anchors.top: parent.top
                    height: 1
                    color: "#2FFFFFFF"
                }

                Canvas {
                    anchors.fill: parent
                    opacity: 0.24
                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        ctx.fillStyle = "#BEB3DC"
                        for (var x = width * 0.43; x < width; x += 28) {
                            for (var y = 18; y < height; y += 28) {
                                ctx.beginPath()
                                ctx.arc(x, y, 0.8, 0, Math.PI * 2)
                                ctx.fill()
                            }
                        }
                    }
                }

                Rectangle {
                    width: 470; height: 470; radius: 235
                    x: hero.width - 300; y: -295
                    color: "#24715BFF"
                    SequentialAnimation on opacity {
                        running: root.parent ? root.parent.visible : root.visible
                        loops: Animation.Infinite
                        NumberAnimation { from: 0.64; to: 1; duration: 3200; easing.type: Easing.InOutSine }
                        NumberAnimation { from: 1; to: 0.64; duration: 3200; easing.type: Easing.InOutSine }
                    }
                }
                Rectangle {
                    width: 300; height: 300; radius: 150
                    x: hero.width - 650; y: 175
                    color: "#187B65FF"
                }
                Rectangle {
                    width: 190; height: 190; radius: 95
                    x: hero.width - 150; y: 155
                    color: "#1A9E88FF"
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 30
                    anchors.rightMargin: 24
                    anchors.topMargin: 24
                    anchors.bottomMargin: 24
                    spacing: 26

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.maximumWidth: 690
                        spacing: 9

                        RowLayout {
                            spacing: 9
                            Rectangle {
                                Layout.preferredWidth: 8; Layout.preferredHeight: 8; radius: 4
                                color: root.readyCount > 0 || root.reviewCount > 0 ? "#F1B35A" : "#4AD1A3"
                                SequentialAnimation on opacity {
                                    running: root.parent ? root.parent.visible : root.visible
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1; to: 0.45; duration: 900; easing.type: Easing.InOutSine }
                                    NumberAnimation { from: 0.45; to: 1; duration: 900; easing.type: Easing.InOutSine }
                                }
                            }
                            Text {
                                text: root.focusLabel()
                                color: root.readyCount > 0 || root.reviewCount > 0 ? "#EAC38B" : "#A9A7B2"
                                font.pixelSize: 9
                                font.weight: Font.Bold
                                font.letterSpacing: 1.2
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.focusTitle()
                            color: Theme.ink
                            font.family: Theme.fontFamily
                            font.pixelSize: 32
                            font.weight: Font.Bold
                            font.letterSpacing: -0.9
                            lineHeight: 1.02
                            renderType: Text.NativeRendering
                            wrapMode: Text.WordWrap
                        }
                        Item { Layout.fillHeight: true }
                        RowLayout {
                            spacing: 9
                            AppButton {
                                text: root.focusButton()
                                iconSource: Theme.icon("arrow-up-right")
                                kind: "primary"
                                accentColor: Theme.accent
                                onClicked: root.navigateRequested(root.focusRoute())
                            }
                            AppButton {
                                visible: root.jobCount > 0
                                text: root.focusRoute() === "applications" ? "Offres" : "Candidatures"
                                iconSource: Theme.icon(root.focusRoute() === "applications" ? "briefcase" : "files")
                                onClicked: root.navigateRequested(root.focusRoute() === "applications" ? "jobs" : "applications")
                            }
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: Math.min(360, hero.width * 0.33)
                        Layout.fillHeight: true
                        radius: 22
                        gradient: Gradient {
                            orientation: Gradient.Vertical
                            GradientStop { position: 0; color: "#C9201B32" }
                            GradientStop { position: 1; color: "#B812101B" }
                        }
                        border.color: "#665986"

                        Rectangle {
                            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                            anchors.leftMargin: 20; anchors.rightMargin: 20
                            height: 1; color: "#30FFFFFF"
                        }

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                Text { Layout.fillWidth: true; text: "Progression"; color: "#F3F1F7"; font.pixelSize: 13; font.weight: Font.DemiBold }
                            }

                            Repeater {
                                model: [
                                    {title: "Recherche"},
                                    {title: "Sélection"},
                                    {title: "Documents"},
                                    {title: "Suivi"}
                                ]
                                delegate: Item {
                                    id: stageRow
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 35
                                    readonly property bool active: index === root.journeyStep()
                                    readonly property bool complete: index < root.journeyStep()

                                    Rectangle {
                                        visible: index < 3
                                        x: 12; y: 24
                                        width: 1; height: 20
                                        color: stageRow.complete ? "#6558D8" : "#373440"
                                    }
                                    Rectangle {
                                        x: 0; y: 1
                                        width: 25; height: 25; radius: 8
                                        gradient: Gradient {
                                            orientation: Gradient.Vertical
                                            GradientStop { position: 0; color: stageRow.active ? Theme.accent : (stageRow.complete ? "#393252" : "#292630") }
                                            GradientStop { position: 1; color: stageRow.active ? Theme.accentDeep : (stageRow.complete ? "#28233C" : "#201F26") }
                                        }
                                        border.color: stageRow.active ? Theme.accentBright : (stageRow.complete ? Theme.accentLine : Theme.lineStrong)
                                        SvgIcon {
                                            anchors.centerIn: parent
                                            visible: stageRow.complete
                                            source: Theme.icon("check")
                                            color: "#A99FFF"
                                            width: 12; height: 12
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            visible: !stageRow.complete
                                            text: index + 1
                                            color: stageRow.active ? "white" : "#777480"
                                            font.pixelSize: 9
                                            font.weight: Font.Bold
                                        }
                                    }
                                    Text {
                                        x: 37; y: 6
                                        width: parent.width - 110
                                        text: modelData.title
                                        color: stageRow.active ? "#F5F3F8" : "#B1AEB8"
                                        font.pixelSize: 11
                                        font.weight: stageRow.active ? Font.DemiBold : Font.Medium
                                        elide: Text.ElideRight
                                    }
                                    Rectangle {
                                        visible: stageRow.active
                                        anchors.right: parent.right
                                        y: 3
                                        width: 68; height: 21; radius: 7
                                        color: Theme.accentSoft
                                        border.color: Theme.accentLine
                                        Text { anchors.centerIn: parent; text: "EN COURS"; color: Theme.accentBright; font.pixelSize: 7; font.weight: Font.Bold; font.letterSpacing: 0.7 }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 13

                MetricCard {
                    Layout.fillWidth: true
                    label: "Offres"
                    value: String(root.jobCount)
                    accent: Theme.accent
                    iconSource: Theme.icon("search")
                    progress: AppBridge.dashboard.analysis_progress || 0
                    interactive: true
                    onActivated: root.navigateRequested("jobs")
                }
                MetricCard {
                    Layout.fillWidth: true
                    label: "À analyser"
                    value: String(root.pendingCount)
                    accent: "#8A72F2"
                    iconSource: Theme.icon("briefcase")
                    progress: Math.min(1, root.pendingCount / Math.max(1, root.jobCount))
                    interactive: true
                    onActivated: root.navigateRequested("jobs")
                }
                MetricCard {
                    Layout.fillWidth: true
                    label: "À relire"
                    value: String(root.readyCount)
                    accent: Theme.success
                    iconSource: Theme.icon("check")
                    progress: AppBridge.dashboard.ready_progress || 0
                    interactive: true
                    onActivated: root.navigateRequested("applications")
                }
                MetricCard {
                    Layout.fillWidth: true
                    label: "Envoyées"
                    value: String(root.sentCount)
                    accent: Theme.blue
                    iconSource: Theme.icon("arrow-up-right")
                    progress: AppBridge.dashboard.sent_progress || 0
                    interactive: true
                    onActivated: root.navigateRequested("applications")
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 5
                columnSpacing: 16
                rowSpacing: 16

                Surface {
                    id: recentApplicationsPanel
                    Layout.columnSpan: 5
                    Layout.fillWidth: true
                    Layout.preferredHeight: (AppBridge.dashboard.recent || []).length > 0 ? 258 : 238
                    padding: 18
                    surfaceEndColor: "#1C1828"

                    SectionTitle {
                        title: "Candidatures récentes"
                        AppButton {
                            text: "Toutes"
                            implicitHeight: 36
                            iconSource: Theme.icon("chevron-right")
                            onClicked: root.navigateRequested("applications")
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        EmptyState {
                            visible: (AppBridge.dashboard.recent || []).length === 0
                            anchors.centerIn: parent
                            iconSource: Theme.icon("files")
                            title: "Aucune candidature"
                        }

                        ColumnLayout {
                            visible: (AppBridge.dashboard.recent || []).length > 0
                            anchors.fill: parent
                            spacing: 3

                            Repeater {
                                model: (AppBridge.dashboard.recent || []).slice(0, 3)
                                delegate: Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 56
                                    radius: 13
                                    color: recentHover.hovered ? Theme.surfaceHover : "transparent"
                                    border.color: recentHover.hovered ? Theme.accentLine : "transparent"

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        spacing: 12

                                        Rectangle {
                                            Layout.preferredWidth: 35; Layout.preferredHeight: 35; radius: 11
                                            color: recentHover.hovered ? Theme.accentLine : Theme.accentSoft
                                            Text { anchors.centerIn: parent; text: modelData.initial; color: Theme.accentDark; font.pixelSize: 11; font.weight: Font.Bold }
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 1
                                            Text { Layout.fillWidth: true; text: modelData.company; color: Theme.ink; font.pixelSize: 12; font.weight: Font.DemiBold; elide: Text.ElideRight }
                                            Text { Layout.fillWidth: true; text: modelData.title; color: Theme.inkMuted; font.pixelSize: 10; elide: Text.ElideRight }
                                        }
                                        Pill { text: modelData.status_label; tone: modelData.tone; compact: true }
                                        Text { text: modelData.updated_at; color: Theme.inkFaint; font.pixelSize: 9 }
                                        SvgIcon { source: Theme.icon("chevron-right"); color: recentHover.hovered ? Theme.accent : Theme.inkFaint; Layout.preferredWidth: 14; Layout.preferredHeight: 14 }
                                    }

                                    HoverHandler { id: recentHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler {
                                        onTapped: {
                                            AppBridge.selectApplication(modelData.id)
                                            root.navigateRequested("applications")
                                        }
                                    }
                                    Behavior on color { ColorAnimation { duration: 130 } }
                                    Behavior on border.color { ColorAnimation { duration: 130 } }
                                }
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }

            }
        }
    }
}
