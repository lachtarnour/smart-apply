import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root
    signal navigateRequested(string route)

    property var sourceKeys: ["serpapi", "francetravail", "linkedin", "welcometothejungle"]
    property var selectedSourceKeys: ["serpapi", "francetravail"]

    function selectedSources() {
        var readiness = AppBridge.diagnostics.source_ready || {}
        return selectedSourceKeys.filter(function(key) { return Boolean(readiness[key]) })
    }

    function setSourceSelected(key, selected) {
        var next = selectedSourceKeys.slice()
        var index = next.indexOf(key)
        if (selected && index < 0) next.push(key)
        if (!selected && index >= 0) next.splice(index, 1)
        selectedSourceKeys = next
    }

    function runSearch() {
        if (!AppBridge.busy) {
            AppBridge.searchJobs(
                queryField.text,
                locationField.text,
                root.selectedSources(),
                maxResults.value,
                freshness.currentValue
            )
        }
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
                title: "Recherche"
                AppButton {
                    text: "Ajouter une offre"
                    iconSource: Theme.icon("plus")
                    kind: "primary"
                    onClicked: root.navigateRequested("manual")
                }
            }

            Surface {
                Layout.fillWidth: true
                padding: 24
                radiusValue: Theme.radiusXLarge
                surfaceEndColor: "#191822"
                SectionTitle {
                    title: "Critères"
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 14
                    rowSpacing: 8
                    FormLabel { text: "POSTES" }
                    FormLabel { text: "LOCALISATION" }
                    AppField {
                        id: queryField
                        Layout.fillWidth: true
                        iconSource: Theme.icon("search")
                        placeholderText: "Data Scientist, ML Engineer…"
                        text: (AppBridge.profile.target_roles || []).join(" OR ")
                        Component.onCompleted: cursorPosition = 0
                        onAccepted: root.runSearch()
                    }
                    AppField {
                        id: locationField
                        Layout.fillWidth: true
                        iconSource: Theme.icon("map-pin")
                        placeholderText: "Paris, France, Londres, Montréal…"
                        text: ""
                        onAccepted: root.runSearch()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 7
                        FormLabel { text: "FRAÎCHEUR" }
                        AppSelect {
                            id: freshness
                            Layout.fillWidth: true
                            implicitHeight: 46
                            textRole: "text"
                            valueRole: "value"
                            model: [
                                {text: "Aujourd’hui", value: "today"},
                                {text: "3 derniers jours", value: "3days"},
                                {text: "7 derniers jours", value: "week"},
                                {text: "30 derniers jours", value: "month"}
                            ]
                            currentIndex: 2
                        }
                    }
                    ColumnLayout {
                        Layout.preferredWidth: 190
                        spacing: 7
                        FormLabel { text: "RÉSULTATS PAR SOURCE" }
                        AppSpinBox { id: maxResults; from: 1; to: 100; value: 20; Layout.fillWidth: true }
                    }
                }
                FormLabel { text: "SOURCES" }
                Flow {
                    Layout.fillWidth: true
                    spacing: 9
                    Repeater {
                        id: sourceRepeater
                        model: [
                            {label: "Google Jobs", symbol: "G", key: "serpapi"},
                            {label: "France Travail", symbol: "F", key: "francetravail"},
                            {label: "LinkedIn", symbol: "in", key: "linkedin"},
                            {label: "Welcome to the Jungle", symbol: "W", key: "welcometothejungle"}
                        ]
                        delegate: ChoiceChip {
                            required property var modelData
                            text: modelData.label
                            symbol: modelData.symbol
                            enabled: AppBridge.diagnostics.source_ready ? Boolean(AppBridge.diagnostics.source_ready[modelData.key]) : false
                            checked: enabled && root.selectedSourceKeys.indexOf(modelData.key) >= 0
                            onToggled: root.setSourceSelected(modelData.key, checked)
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: root.selectedSources().length + " source" + (root.selectedSources().length === 1 ? " sélectionnée" : "s sélectionnées")
                        color: Theme.inkMuted
                        font.pixelSize: 12
                    }
                    AppButton {
                        text: AppBridge.canCancel ? "Annuler" : "Rechercher"
                        iconSource: Theme.icon(AppBridge.canCancel ? "x" : "search")
                        kind: AppBridge.canCancel ? "danger" : "primary"
                        enabled: !AppBridge.busy || AppBridge.canCancel
                        onClicked: {
                            if (AppBridge.canCancel)
                                AppBridge.cancelCurrentTask()
                            else
                                root.runSearch()
                        }
                    }
                }
            }

            Surface {
                Layout.fillWidth: true
                Layout.preferredHeight: 164
                padding: 22
                surfaceColor: "#17161F"
                surfaceEndColor: "#201D31"
                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 22
                    RowLayout {
                        Layout.preferredWidth: Math.max(390, parent.width * 0.42)
                        spacing: 14
                        Rectangle {
                            Layout.preferredWidth: 46; Layout.preferredHeight: 46; radius: 14
                            color: Theme.accentSoft
                            border.color: Theme.accentLine
                            SvgIcon { anchors.centerIn: parent; source: Theme.icon("briefcase"); color: Theme.accentDark; width: 20; height: 20 }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 7
                            Text { text: "Analyse des offres"; color: Theme.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
                            RowLayout {
                                spacing: 9
                                Text { text: "Offres à retenir"; color: Theme.inkMuted; font.pixelSize: 11; font.weight: Font.Medium }
                                AppSpinBox { id: topK; from: 1; to: 100; value: AppBridge.topK; Layout.preferredWidth: 130; onValueModified: AppBridge.setTopK(value) }
                                AppButton { text: "Analyser"; kind: "primary"; enabled: !AppBridge.busy; onClicked: AppBridge.processPending(topK.value) }
                            }
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; Layout.topMargin: 7; Layout.bottomMargin: 7; color: Theme.lineStrong }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Repeater {
                            model: [
                                {label: "OFFRES", value: AppBridge.dashboard.jobs || 0},
                                {label: "À ANALYSER", value: AppBridge.dashboard.pending || 0},
                                {label: "DOSSIERS", value: AppBridge.dashboard.ready || 0}
                            ]
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 2
                                Text { Layout.alignment: Qt.AlignHCenter; text: String(modelData.value); color: Theme.ink; font.pixelSize: 22; font.weight: Font.Bold }
                                Text { Layout.alignment: Qt.AlignHCenter; text: modelData.label; color: Theme.inkMuted; font.pixelSize: 8; font.weight: Font.Bold; font.letterSpacing: 0.7 }
                            }
                        }
                        AppButton {
                            text: "Offres"
                            iconSource: Theme.icon("chevron-right")
                            implicitHeight: 40
                            onClicked: root.navigateRequested("jobs")
                        }
                    }
                }
            }

            Surface {
                visible: (AppBridge.activity.title || "").length > 0
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? 132 : 0
                padding: 18
                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Rectangle {
                        Layout.preferredWidth: 44; Layout.preferredHeight: 44; radius: 14
                        color: AppBridge.activity.kind === "success" ? Theme.successSoft : AppBridge.activity.kind === "danger" ? Theme.dangerSoft : Theme.accentSoft
                        SvgIcon { anchors.centerIn: parent; source: AppBridge.activity.kind === "success" ? Theme.icon("check") : Theme.icon("arrow-up-right"); color: AppBridge.activity.kind === "success" ? Theme.success : Theme.accent; width: 20; height: 20 }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 3
                        Text { text: AppBridge.activity.title || "Dernière opération"; color: Theme.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                        Text { visible: (AppBridge.activity.message || "").length > 0; text: AppBridge.activity.message || ""; color: Theme.inkMuted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                    ColumnLayout {
                        visible: (AppBridge.activity.fetched || 0) > 0
                        Text { text: AppBridge.activity.fetched || 0; color: Theme.ink; font.pixelSize: 23; font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                        Text { text: "trouvées"; color: Theme.inkMuted; font.pixelSize: 10 }
                    }
                    ColumnLayout {
                        visible: (AppBridge.activity.persisted || 0) > 0
                        Text { text: AppBridge.activity.persisted || 0; color: Theme.accent; font.pixelSize: 23; font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                        Text { text: "enregistrées"; color: Theme.inkMuted; font.pixelSize: 10 }
                    }
                }
            }
        }
    }
}
