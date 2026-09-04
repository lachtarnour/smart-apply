import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root
    signal navigateRequested(string route)
    property int selectedId: AppBridge.currentApplication.id || 0

    Timer {
        id: searchTimer
        interval: 260
        onTriggered: AppBridge.loadApplications(searchField.text, filter.currentValue || "")
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 18

        PageHeader {
            Layout.fillWidth: true
            title: "Candidatures"
            AppButton { text: "Ajouter une offre"; iconSource: Theme.icon("plus"); kind: "primary"; onClicked: root.navigateRequested("manual") }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            AppField {
                id: searchField
                Layout.fillWidth: true
                iconSource: Theme.icon("search")
                placeholderText: "Rechercher une entreprise ou un poste…"
                onTextChanged: searchTimer.restart()
            }
            AppSelect {
                id: filter
                implicitHeight: 48
                implicitWidth: 200
                textRole: "label"
                valueRole: "value"
                model: [{label: "Tous les statuts", value: ""}].concat(AppBridge.applicationStatuses)
                onActivated: AppBridge.loadApplications(searchField.text, currentValue)
            }
            Pill { text: AppBridge.applications.length + " candidature" + (AppBridge.applications.length === 1 ? "" : "s"); tone: "accent" }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            Surface {
                Layout.preferredWidth: Math.max(400, root.width * 0.39)
                Layout.fillHeight: true
                padding: 10
                elevated: false
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    EmptyState {
                        visible: AppBridge.applications.length === 0
                        anchors.centerIn: parent
                        iconSource: Theme.icon("files")
                        title: "Aucune candidature"
                        message: "Créez-en depuis une offre."
                    }
                    ListView {
                        id: applicationsList
                        anchors.fill: parent
                        visible: AppBridge.applications.length > 0
                        model: AppBridge.applications
                        clip: true
                        spacing: 7
                        reuseItems: true
                        cacheBuffer: 360
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: AppScrollBar { }
                        delegate: Rectangle {
                            required property var modelData
                            width: applicationsList.width
                            height: 118
                            radius: 15
                            color: root.selectedId === modelData.id ? Theme.accentSoft : (hover.hovered ? Theme.surfaceHover : "transparent")
                            border.color: root.selectedId === modelData.id ? Theme.accentLine : "transparent"
                            border.width: 1
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 13
                                spacing: 5
                                RowLayout {
                                    Layout.fillWidth: true
                                    Rectangle {
                                        Layout.preferredWidth: 34; Layout.preferredHeight: 34; radius: 11
                                        color: root.selectedId === modelData.id ? Theme.accentLine : Theme.neutralSoft
                                        Text { anchors.centerIn: parent; text: modelData.initial; color: Theme.accentDark; font.pixelSize: 12; font.weight: Font.Bold }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 1
                                        Text { Layout.fillWidth: true; text: modelData.company; color: Theme.ink; font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideRight }
                                        Text { Layout.fillWidth: true; text: modelData.title; color: Theme.inkMuted; font.pixelSize: 11; elide: Text.ElideRight }
                                    }
                                    Pill { text: modelData.status_label; tone: modelData.tone; compact: true }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    SvgIcon { source: Theme.icon("chevron-right"); color: Theme.accent; Layout.preferredWidth: 13; Layout.preferredHeight: 13 }
                                    Text { Layout.fillWidth: true; text: modelData.next_action; color: Theme.inkMuted; font.pixelSize: 10; elide: Text.ElideRight }
                                    Text { text: modelData.updated_at; color: Theme.inkFaint; font.pixelSize: 9 }
                                }
                            }
                            HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: AppBridge.selectApplication(modelData.id) }
                            Behavior on color { ColorAnimation { duration: 130 } }
                        }
                    }
                }
            }

            Surface {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: 24
                elevated: false
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    EmptyState {
                        visible: !AppBridge.currentApplication.id
                        anchors.centerIn: parent
                        iconSource: Theme.icon("sparkle")
                        title: "Sélectionnez une candidature"
                    }
                    ColumnLayout {
                        visible: Boolean(AppBridge.currentApplication.id)
                        anchors.fill: parent
                        spacing: 11
                        RowLayout {
                            Layout.fillWidth: true
                            Pill { text: AppBridge.currentApplication.status_label || ""; tone: AppBridge.currentApplication.tone || "neutral" }
                            Item { Layout.fillWidth: true }
                            AppButton { visible: Boolean(AppBridge.currentApplication.job_url); text: "Offre originale"; iconSource: Theme.icon("arrow-up-right"); implicitHeight: 38; onClicked: AppBridge.openUrl(AppBridge.currentApplication.job_url) }
                        }
                        Text { Layout.fillWidth: true; text: AppBridge.currentApplication.title || ""; color: Theme.ink; font.pixelSize: 24; font.weight: Font.Bold; wrapMode: Text.WordWrap }
                        Text { Layout.fillWidth: true; text: (AppBridge.currentApplication.company || "") + "  ·  " + (AppBridge.currentApplication.location || "Lieu non indiqué"); color: Theme.inkMuted; font.pixelSize: 14; wrapMode: Text.WordWrap }
                        Text {
                            Layout.fillWidth: true
                            visible: Boolean(AppBridge.currentApplication.folder_identifier)
                            text: "Identifiant : " + (AppBridge.currentApplication.folder_identifier || "")
                            color: Theme.inkFaint
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: nextAction.implicitHeight + 22
                            radius: 12
                            color: Theme.accentSoft
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 11; spacing: 9
                                SvgIcon { source: Theme.icon("chevron-right"); color: Theme.accentDark; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
                                Text { id: nextAction; Layout.fillWidth: true; text: AppBridge.currentApplication.next_action || ""; color: Theme.accentDark; font.pixelSize: 12; font.weight: Font.DemiBold; wrapMode: Text.WordWrap }
                            }
                        }
                        RowLayout {
                            visible: (AppBridge.currentApplication.match_reasons || []).length > 0 || (AppBridge.currentApplication.risks || []).length > 0 || (AppBridge.currentApplication.warnings || []).length > 0
                            Layout.fillWidth: true
                            spacing: 9
                            Rectangle {
                                visible: (AppBridge.currentApplication.match_reasons || []).length > 0
                                Layout.fillWidth: true
                                Layout.preferredWidth: 1
                                implicitHeight: profileMatches.implicitHeight + 22
                                radius: 12
                                color: Theme.accentSoft
                                border.color: Theme.accentLine
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 11; spacing: 9
                                    SvgIcon { source: Theme.icon("check"); color: Theme.accentDark; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 4
                                        Text { text: "Correspond à votre profil"; color: Theme.ink; font.pixelSize: 12; font.weight: Font.DemiBold }
                                        Text { id: profileMatches; Layout.fillWidth: true; text: "• " + (AppBridge.currentApplication.match_reasons || []).join("\n• "); color: Theme.inkSoft; font.pixelSize: 11; wrapMode: Text.WordWrap }
                                    }
                                }
                            }
                            Rectangle {
                                visible: (AppBridge.currentApplication.risks || []).length > 0 || (AppBridge.currentApplication.warnings || []).length > 0
                                Layout.fillWidth: true
                                Layout.preferredWidth: 1
                                implicitHeight: applicationWarnings.implicitHeight + 22
                                radius: 12
                                color: Theme.warningSoft
                                border.color: Theme.warning
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 11; spacing: 9
                                    SvgIcon { source: Theme.icon("alert-circle"); color: Theme.warning; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
                                    Text {
                                        id: applicationWarnings
                                        Layout.fillWidth: true
                                        text: "Points à vérifier\n• " + (AppBridge.currentApplication.risks || []).concat(AppBridge.currentApplication.warnings || []).join("\n• ")
                                        color: Theme.inkSoft
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }
                        }
                        TabBar {
                            id: tabs
                            Layout.fillWidth: true
                            Layout.preferredHeight: 43
                            spacing: 3
                            padding: 4
                            background: Rectangle { color: Theme.surfaceMuted; radius: 12 }
                            TabButton {
                                id: letterTab
                                text: "Lettre"
                                contentItem: Text { text: letterTab.text; color: letterTab.checked ? Theme.accentDark : Theme.inkMuted; font.pixelSize: 12; font.weight: letterTab.checked ? Font.DemiBold : Font.Medium; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                background: Rectangle { color: letterTab.checked ? Theme.surfaceHover : "transparent"; radius: 9; border.color: letterTab.checked ? Theme.accentLine : "transparent" }
                            }
                            TabButton {
                                id: trackingTab
                                text: "Suivi"
                                contentItem: Text { text: trackingTab.text; color: trackingTab.checked ? Theme.accentDark : Theme.inkMuted; font.pixelSize: 12; font.weight: trackingTab.checked ? Font.DemiBold : Font.Medium; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                background: Rectangle { color: trackingTab.checked ? Theme.surfaceHover : "transparent"; radius: 9; border.color: trackingTab.checked ? Theme.accentLine : "transparent" }
                            }
                        }
                        StackLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            currentIndex: tabs.currentIndex
                            ColumnLayout {
                                spacing: 8
                                Text { Layout.fillWidth: true; text: AppBridge.currentApplication.letter_subject || "Lettre de motivation"; color: Theme.inkSoft; font.pixelSize: 13; font.weight: Font.DemiBold; wrapMode: Text.WordWrap }
                                DocumentPreview { Layout.fillWidth: true; Layout.fillHeight: true; text: AppBridge.currentApplication.letter_body || "" }
                            }
                            ColumnLayout {
                                spacing: 9
                                RowLayout {
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 5
                                        FormLabel { text: "STATUT" }
                                        AppSelect {
                                            id: trackingStatus
                                            Layout.fillWidth: true
                                            implicitHeight: 44
                                            textRole: "label"
                                            valueRole: "value"
                                            model: AppBridge.applicationStatuses
                                            currentIndex: Math.max(0, indexOfValue(AppBridge.currentApplication.status || ""))
                                        }
                                    }
                                }
                                FormLabel { text: "NOTES DE SUIVI" }
                                AppTextArea { id: notes; Layout.fillWidth: true; Layout.fillHeight: true; text: AppBridge.currentApplication.notes || ""; placeholderText: "Relance prévue, retour reçu, contexte utile…" }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Item { Layout.fillWidth: true }
                                    AppButton { text: "Enregistrer"; kind: "primary"; onClicked: AppBridge.updateApplication(AppBridge.currentApplication.id, trackingStatus.currentValue, notes.text, false) }
                                }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }
                        FormLabel { text: "DOCUMENTS" }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 8
                            Repeater {
                                model: [
                                    {label: "CV PDF", path: AppBridge.currentApplication.cv_pdf_path || ""},
                                    {label: "CV Word", path: AppBridge.currentApplication.cv_docx_path || ""},
                                    {label: "Lettre", path: AppBridge.currentApplication.letter_pdf_path || ""}
                                ].filter(function(v) { return v.path.length > 0 })
                                delegate: AppButton { required property var modelData; text: modelData.label; implicitHeight: 36; onClicked: AppBridge.openPath(modelData.path) }
                            }
                            AppButton {
                                visible: Boolean(AppBridge.currentApplication.id)
                                text: "Dossier"
                                iconSource: Theme.icon("folder")
                                implicitHeight: 36
                                onClicked: AppBridge.openApplicationFolder(Number(AppBridge.currentApplication.id))
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 9
                            AppButton { visible: Boolean(AppBridge.currentApplication.form_url); text: "Formulaire"; iconSource: Theme.icon("arrow-up-right"); onClicked: AppBridge.openUrl(AppBridge.currentApplication.form_url) }
                            Item { Layout.fillWidth: true }
                            AppButton {
                                visible: Boolean(AppBridge.currentApplication.form_url) && !AppBridge.currentApplication.form_submitted_at && AppBridge.currentApplication.status !== "sent"
                                text: "Marquer comme envoyée"; kind: "primary"; iconSource: Theme.icon("check"); onClicked: formSentDialog.open()
                            }
                        }
                    }
                }
            }
        }
    }

    ConfirmDialog {
        id: formSentDialog
        anchors.centerIn: parent
        heading: "Confirmer l’envoi"
        message: "La date d’envoi sera enregistrée dans le suivi."
        confirmText: "Confirmer"
        onAccepted: AppBridge.updateApplication(AppBridge.currentApplication.id, AppBridge.currentApplication.status, AppBridge.currentApplication.notes || "", true)
    }
}
