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
        spacing: 14

        PageHeader {
            Layout.fillWidth: true
            eyebrow: "ESPACE DE CANDIDATURE"
            title: "Candidatures"
            subtitle: "Consultez l’adéquation avec votre profil, vérifiez les points sensibles et suivez chaque envoi."
            AppButton { text: "Ajouter une offre"; iconSource: Theme.icon("plus"); kind: "primary"; onClicked: root.navigateRequested("manual") }
        }

        Surface {
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            padding: 11
            elevated: false
            surfaceColor: Theme.surfaceMuted
            surfaceEndColor: Theme.surface
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
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
                Rectangle {
                    Layout.preferredWidth: applicationCount.implicitWidth + 22
                    Layout.preferredHeight: 32
                    radius: 16
                    color: Theme.neutralSoft
                    border.color: Theme.line
                    Text {
                        id: applicationCount
                        anchors.centerIn: parent
                        text: AppBridge.applications.length + " candidature" + (AppBridge.applications.length === 1 ? "" : "s")
                        color: Theme.inkMuted
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            Surface {
                Layout.preferredWidth: Math.max(360, root.width * 0.31)
                Layout.maximumWidth: 440
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
                            height: 108
                            radius: 15
                            color: root.selectedId === modelData.id ? Theme.accentSoft : (hover.hovered ? Theme.surfaceHover : "transparent")
                            border.color: root.selectedId === modelData.id ? Theme.accentLine : "transparent"
                            border.width: 1
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 12
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
                padding: 0
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
                        spacing: 0
                        Flickable {
                            id: applicationDetailViewport
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            contentWidth: width
                            contentHeight: applicationDetailContent.implicitHeight + 40
                            boundsBehavior: Flickable.StopAtBounds
                            clip: true
                            ScrollBar.vertical: AppScrollBar { }
                            ColumnLayout {
                                id: applicationDetailContent
                                width: applicationDetailViewport.width - 48
                                x: 24
                                y: 22
                                spacing: 12
                                RowLayout {
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 3
                                        Text { Layout.fillWidth: true; text: AppBridge.currentApplication.company || "Entreprise non indiquée"; color: Theme.accentBright; font.pixelSize: 11; font.weight: Font.DemiBold; elide: Text.ElideRight }
                                        Text { Layout.fillWidth: true; text: AppBridge.currentApplication.title || ""; color: Theme.ink; font.pixelSize: 23; font.weight: Font.Bold; wrapMode: Text.WordWrap; lineHeight: 0.95 }
                                        Text { Layout.fillWidth: true; text: (AppBridge.currentApplication.location || "Lieu non indiqué") + (AppBridge.currentApplication.folder_identifier ? "  ·  Dossier " + AppBridge.currentApplication.folder_identifier : ""); color: Theme.inkMuted; font.pixelSize: 10; elide: Text.ElideRight }
                                    }
                                    ColumnLayout {
                                        spacing: 7
                                        Pill { Layout.alignment: Qt.AlignRight; text: AppBridge.currentApplication.status_label || ""; tone: AppBridge.currentApplication.tone || "neutral" }
                                        AppButton { visible: Boolean(AppBridge.currentApplication.job_url); text: "Offre"; iconSource: Theme.icon("arrow-up-right"); implicitHeight: 36; onClicked: AppBridge.openUrl(AppBridge.currentApplication.job_url) }
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: nextAction.implicitHeight + 24
                                    radius: 13
                                    color: Theme.accentSoft
                                    border.color: Theme.accentLine
                                    RowLayout {
                                        anchors.fill: parent; anchors.margins: 12; spacing: 9
                                        SvgIcon { source: Theme.icon("chevron-right"); color: Theme.accentBright; Layout.preferredWidth: 15; Layout.preferredHeight: 15 }
                                        Text { id: nextAction; Layout.fillWidth: true; text: AppBridge.currentApplication.next_action || ""; color: Theme.accentDark; font.pixelSize: 11; font.weight: Font.DemiBold; wrapMode: Text.WordWrap }
                                    }
                                }

                                Rectangle {
                                    visible: (AppBridge.currentApplication.match_reasons || []).length > 0
                                    Layout.fillWidth: true
                                    implicitHeight: profileMatchesContent.implicitHeight + 28
                                    radius: 15
                                    color: Theme.successSoft
                                    border.color: "#285B4D"
                                    ColumnLayout {
                                        id: profileMatchesContent
                                        anchors.fill: parent; anchors.margins: 14; spacing: 9
                                        RowLayout {
                                            Layout.fillWidth: true; spacing: 8
                                            SvgIcon { source: Theme.icon("sparkle"); color: Theme.success; Layout.preferredWidth: 15; Layout.preferredHeight: 15 }
                                            Text { text: "Correspond à votre profil"; color: Theme.success; font.pixelSize: 11; font.weight: Font.DemiBold }
                                        }
                                        Repeater {
                                            model: AppBridge.currentApplication.match_reasons || []
                                            delegate: RowLayout {
                                                required property var modelData
                                                Layout.fillWidth: true; spacing: 8
                                                Rectangle { Layout.preferredWidth: 5; Layout.preferredHeight: 5; radius: 3; color: Theme.success }
                                                Text { Layout.fillWidth: true; text: modelData; color: Theme.inkSoft; font.pixelSize: 10; wrapMode: Text.WordWrap; lineHeight: 1.2 }
                                            }
                                        }
                                    }
                                }

                                Rectangle {
                                    visible: (AppBridge.currentApplication.risks || []).length > 0 || (AppBridge.currentApplication.warnings || []).length > 0
                                    Layout.fillWidth: true
                                    implicitHeight: applicationWarningsContent.implicitHeight + 28
                                    radius: 15
                                    color: Theme.warningSoft
                                    border.color: "#594326"
                                    ColumnLayout {
                                        id: applicationWarningsContent
                                        anchors.fill: parent; anchors.margins: 14; spacing: 9
                                        RowLayout {
                                            Layout.fillWidth: true; spacing: 8
                                            SvgIcon { source: Theme.icon("alert-circle"); color: Theme.warning; Layout.preferredWidth: 15; Layout.preferredHeight: 15 }
                                            Text { text: "Points à vérifier"; color: Theme.warning; font.pixelSize: 11; font.weight: Font.DemiBold }
                                        }
                                        Repeater {
                                            model: (AppBridge.currentApplication.risks || []).concat(AppBridge.currentApplication.warnings || [])
                                            delegate: RowLayout {
                                                required property var modelData
                                                Layout.fillWidth: true; spacing: 8
                                                Rectangle { Layout.preferredWidth: 5; Layout.preferredHeight: 5; radius: 3; color: Theme.warning }
                                                Text { Layout.fillWidth: true; text: modelData; color: Theme.inkSoft; font.pixelSize: 10; wrapMode: Text.WordWrap; lineHeight: 1.2 }
                                            }
                                        }
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: trackingContent.implicitHeight + 28
                                    radius: 15
                                    color: Theme.surfaceMuted
                                    border.color: Theme.line
                                    ColumnLayout {
                                        id: trackingContent
                                        anchors.fill: parent; anchors.margins: 14; spacing: 10
                                        RowLayout {
                                            Layout.fillWidth: true
                                            FormLabel { text: "SUIVI DE LA CANDIDATURE" }
                                            Item { Layout.fillWidth: true }
                                            AppButton { text: "Enregistrer"; kind: "primary"; implicitHeight: 36; onClicked: AppBridge.updateApplication(AppBridge.currentApplication.id, trackingStatus.currentValue, notes.text, false) }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true; spacing: 10
                                            ColumnLayout {
                                                Layout.preferredWidth: 210; spacing: 5
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
                                            ColumnLayout {
                                                Layout.fillWidth: true; spacing: 5
                                                FormLabel { text: "NOTES" }
                                                AppTextArea { id: notes; Layout.fillWidth: true; Layout.preferredHeight: 92; text: AppBridge.currentApplication.notes || ""; placeholderText: "Relance prévue, retour reçu, contexte utile…" }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: 20; Layout.rightMargin: 20
                            Layout.topMargin: 12; Layout.bottomMargin: 12
                            spacing: 8
                            Repeater {
                                model: [
                                    {label: "CV PDF", path: AppBridge.currentApplication.cv_pdf_path || ""},
                                    {label: "CV Word", path: AppBridge.currentApplication.cv_docx_path || ""},
                                    {label: "Lettre PDF", path: AppBridge.currentApplication.letter_pdf_path || ""}
                                ].filter(function(v) { return v.path.length > 0 })
                                delegate: AppButton { required property var modelData; text: modelData.label; implicitHeight: 38; onClicked: AppBridge.openPath(modelData.path) }
                            }
                            AppButton { text: "Dossier"; iconSource: Theme.icon("folder"); implicitHeight: 38; onClicked: AppBridge.openApplicationFolder(Number(AppBridge.currentApplication.id)) }
                            Item { Layout.fillWidth: true }
                            AppButton { visible: Boolean(AppBridge.currentApplication.form_url); text: "Formulaire"; iconSource: Theme.icon("arrow-up-right"); implicitHeight: 38; onClicked: AppBridge.openUrl(AppBridge.currentApplication.form_url) }
                            AppButton {
                                visible: Boolean(AppBridge.currentApplication.form_url) && !AppBridge.currentApplication.form_submitted_at && AppBridge.currentApplication.status !== "sent"
                                text: "Marquer envoyée"; kind: "primary"; iconSource: Theme.icon("check"); implicitHeight: 38; onClicked: formSentDialog.open()
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
