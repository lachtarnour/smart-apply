import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root
    signal navigateRequested(string route)

    function connectedSourceCount() {
        var sources = AppBridge.diagnostics.sources || []
        var count = 0
        for (var i = 0; i < sources.length; ++i) if (sources[i].ready) count += 1
        return count
    }

    function sourceStatusText(source) {
        if (source.state === "available") return "Disponible"
        if (source.state === "checking") return "Vérification…"
        if (source.state === "unavailable") return "Indisponible"
        return "À configurer"
    }

    function sourceStatusTone(source) {
        if (source.state === "available") return "success"
        if (source.state === "unavailable") return "danger"
        return "warning"
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight + 56
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: AppScrollBar { }
        ColumnLayout {
            id: content
            width: parent.width - 12
            spacing: 18
            PageHeader {
                Layout.fillWidth: true
                title: "Réglages"
                AppButton { text: "Actualiser"; iconSource: Theme.icon("refresh"); onClicked: AppBridge.refreshDiagnostics() }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 5
                columnSpacing: 16; rowSpacing: 16
                Surface {
                    Layout.columnSpan: 3
                    Layout.fillWidth: true
                    Layout.preferredHeight: 426
                    surfaceEndColor: "#191821"
                    SectionTitle { title: "Stockage local" }
                    Repeater {
                        model: [
                            {label: "Base de données", path: AppBridge.diagnostics.database_path || "", icon: Theme.icon("database"), ready: AppBridge.diagnostics.database_exists},
                            {label: "CV et lettres", path: AppBridge.diagnostics.output_dir || "", icon: Theme.icon("folder"), ready: true},
                            {label: "Profil", path: AppBridge.diagnostics.profile_dir || "", icon: Theme.icon("user"), ready: true},
                            {label: "Configuration", path: AppBridge.diagnostics.env_file || "", icon: Theme.icon("settings"), ready: true}
                        ]
                        delegate: Rectangle {
                            required property var modelData
                            activeFocusOnTab: true
                            Accessible.role: Accessible.Button
                            Accessible.name: "Ouvrir " + modelData.label
                            Layout.fillWidth: true
                            Layout.preferredHeight: 70
                            radius: 14
                            color: hover.hovered ? Theme.surfaceHover : Theme.surfaceMuted
                            border.color: hover.hovered ? Theme.accentLine : Theme.line
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 12
                                Rectangle { Layout.preferredWidth: 38; Layout.preferredHeight: 38; radius: 12; color: Theme.accentSoft; SvgIcon { anchors.centerIn: parent; source: modelData.icon; color: Theme.accentDark; width: 18; height: 18 } }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 2
                                    Text { text: modelData.label; color: Theme.inkSoft; font.pixelSize: 13; font.weight: Font.DemiBold }
                                    Text { Layout.fillWidth: true; text: modelData.path; color: Theme.inkMuted; font.pixelSize: 10; elide: Text.ElideMiddle }
                                }
                                SvgIcon { source: Theme.icon("arrow-up-right"); color: Theme.accent; Layout.preferredWidth: 13; Layout.preferredHeight: 13 }
                            }
                            HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: AppBridge.openPath(modelData.path) }
                            Keys.onReturnPressed: AppBridge.openPath(modelData.path)
                            Keys.onEnterPressed: AppBridge.openPath(modelData.path)
                            Keys.onSpacePressed: AppBridge.openPath(modelData.path)
                            Accessible.onPressAction: AppBridge.openPath(modelData.path)
                        }
                    }
                }
                ColumnLayout {
                    Layout.columnSpan: 2
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    spacing: 16
                    Surface {
                        Layout.fillWidth: true
                        padding: 20
                        surfaceEndColor: "#191821"
                        SectionTitle { title: "Sources"; caption: root.connectedSourceCount() + " sur " + (AppBridge.diagnostics.sources || []).length + " vérifiées disponibles" }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 7
                            radius: 4
                            color: Theme.neutralSoft
                            Rectangle {
                                width: parent.width * (AppBridge.diagnostics.sources && AppBridge.diagnostics.sources.length > 0 ? root.connectedSourceCount() / AppBridge.diagnostics.sources.length : 0)
                                height: parent.height
                                radius: parent.radius
                                color: Theme.success
                                Behavior on width { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }
                            }
                        }
                        Repeater {
                            model: AppBridge.diagnostics.sources || []
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    Text { Layout.fillWidth: true; text: modelData.label; color: Theme.inkSoft; font.pixelSize: 12 }
                                    Text { Layout.fillWidth: true; text: modelData.message || ""; color: Theme.inkMuted; font.pixelSize: 9; elide: Text.ElideRight }
                                }
                                Pill { text: root.sourceStatusText(modelData); tone: root.sourceStatusTone(modelData); compact: true }
                            }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 158
                        radius: 22; clip: true
                        border.color: "#4B435E"
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: "#191620" }
                            GradientStop { position: 1; color: "#2E2546" }
                        }
                        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 20; anchors.rightMargin: 20; anchors.top: parent.top; height: 1; color: "#2BFFFFFF" }
                        Rectangle { width: 180; height: 180; radius: 90; x: parent.width - 88; y: -88; color: "#27745DFF" }
                        Canvas {
                            anchors.fill: parent; opacity: 0.16
                            onPaint: { var c = getContext("2d"); c.fillStyle = "#8A84A0"; for (var x = 16; x < width; x += 24) for (var y = 16; y < height; y += 24) { c.beginPath(); c.arc(x, y, .7, 0, Math.PI * 2); c.fill() } }
                        }
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 20; spacing: 5
                            RowLayout {
                                spacing: 10
                                Image {
                                    Layout.preferredWidth: 38
                                    Layout.preferredHeight: 38
                                    source: Qt.resolvedUrl("../../resources/app_icon.svg")
                                    smooth: true
                                    mipmap: true
                                }
                                ColumnLayout {
                                    spacing: 1
                                    Text { text: "Élan"; color: "white"; font.pixelSize: 17; font.weight: Font.Bold }
                                    Text { text: "Version 0.1.0 · macOS"; color: "#AAA6B6"; font.pixelSize: 10 }
                                }
                            }
                            Item { Layout.fillHeight: true }
                            Text { Layout.fillWidth: true; text: "Modèle utilisé  ·  " + (AppBridge.diagnostics.llm_provider || "") + " / " + (AppBridge.diagnostics.llm_model || ""); color: "#D1CDDA"; font.pixelSize: 11; wrapMode: Text.WordWrap }
                        }
                    }
                }
            }
        }
    }
}
